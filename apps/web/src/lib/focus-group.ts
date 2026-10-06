import type { InterviewModelCatalogEntry } from "./api";
import { isInterviewModelSelectable } from "./interview-models";

// Mirrors apps/api/src/services/focus_group.py. The student approves a number before
// anything is spent, so the number they see has to be the one the server bills
// against; a pytest pins these two copies together.
export const MIN_PERSONAS = 3;
export const MAX_PERSONAS = 8;
export const MAX_ROUNDS = 12;
// Lin fix 4: one core question per stage, plus follow-up probes. Mirrors focus_group.py.
export const CORE_QUESTIONS = 5;
export const DEFAULT_PROBES = 3;
export const ESTIMATED_PROMPT_TOKENS_PER_TURN = 2000;
export const ESTIMATED_COMPLETION_TOKENS_PER_TURN = 400;

export const FOCUS_GROUP_STAGES = [
  "icebreaker",
  "space_needs",
  "concept",
  "price_reactions",
  "close",
] as const;

export type FocusGroupStage = (typeof FOCUS_GROUP_STAGES)[number];

export const FOCUS_GROUP_STAGE_LABELS: Record<FocusGroupStage, string> = {
  icebreaker: "Icebreaker",
  space_needs: "General space needs",
  concept: "The Tahoe Mini concept",
  price_reactions: "Price reactions",
  close: "Close",
};

// Lin: every output says what it is. Mirrors REHEARSAL_LABEL in focus_group.py.
export const REHEARSAL_LABEL = "Synthetic rehearsal - not PA3.5 live fieldwork";

export type FocusGroupAnswer = {
  turn_id?: string;
  persona_id: string;
  text: string;
  // "silent": the question was addressed to someone else. Intended, never an error.
  status: "answered" | "missing" | "silent";
  error: { code: string; message: string } | null;
};

export type FocusGroupRoom = {
  demo?: boolean;
  provisional?: boolean;
  room_id: string;
  status: "running" | "completed" | "failed" | "budget_stopped" | "cancelled";
  revision: number;
  stage: FocusGroupStage;
  stages_reached: FocusGroupStage[];
  persona_ids: string[];
  model: string;
  max_rounds: number;
  estimated_cost_usd: string;
  complete: boolean;
  rounds: {
    index: number;
    turn_id?: string;
    stage: FocusGroupStage;
    question: string;
    /** derived: a room from before Introduce/Reveal, where the stage itself showed it. */
    stimulus?: { kind: RevealKind; text: string; derived?: boolean };
    kind?: "core" | "probe";
    recipients?: string[] | null;
    answers: FocusGroupAnswer[];
  }[];
  concept_card?: ConceptCard;
  allowance?: Allowance;
  estimated_total_cost_usd?: string;
  extension_cost_per_round_usd?: string | null;
  participants?: { persona_id: string; card: PersonaCard | null }[];
  shared?: SharedStimulus[];
  memo: { themes: unknown[] | null } | null;
  manual_memo?: ManualMemo | null;
  manual_memo_check?: { saved: boolean; complete: boolean; problems: string[] };
  session_usage: { cost_usd: string };
  error: { code: string; message: string; stage?: string; missing?: unknown[] } | null;
};

export type FocusGroupMemo = {
  room_id: string;
  revision: string;
  eligible: boolean;
  available: boolean;
  stale: boolean;
  message: string;
  answered_turns: number;
  estimated_cost_usd: string;
  model: string;
  saved: {
    attempt: number;
    outcome?: string;
    cost_usd?: string;
    reason?: string;
    message?: string;
    budget_stop?: string;
    themes:
      | {
          label: string;
          synthesis: string;
          quote: string;
          persona_id: string;
          sentiment: string;
          located_at: { persona_id: string; round: number; stage: FocusGroupStage; question: string };
        }[]
      | null;
    surprise?: { summary: string; quote: string; persona_id: string };
    // The server requires persona_id on an option and refuses the memo without it; display
    // still reads located_at, which is the transcript position it was verified against.
    answer_options?: {
      text: string;
      persona_id: string;
      located_at: { persona_id: string; round: number; stage: FocusGroupStage; question: string };
    }[];
  } | null;
};

/** Personas times rounds, not one call — the whole room is what gets charged. */
export function estimateFocusGroupCost(
  personaCount: number,
  rounds: number,
  model: InterviewModelCatalogEntry | undefined
) {
  if (!model) return 0;
  const perTurn =
    (model.prompt_price_per_million * ESTIMATED_PROMPT_TOKENS_PER_TURN +
      model.completion_price_per_million * ESTIMATED_COMPLETION_TOKENS_PER_TURN) /
    1_000_000;
  return perTurn * personaCount * rounds;
}

export function formatFocusGroupCostEstimate(costUsd: number) {
  return `$${costUsd.toFixed(3)}`;
}

/** Why the start control is refusing, in the words the student should see. */
export function focusGroupSetupRefusal(setup: {
  personaIds: string[];
  rounds: number;
  model?: InterviewModelCatalogEntry;
  expensiveOptIn: boolean;
}): string | null {
  const unique = new Set(setup.personaIds);
  if (unique.size !== setup.personaIds.length) {
    return "Each persona can only take one seat in the room.";
  }
  if (setup.personaIds.length < MIN_PERSONAS) {
    return `A focus group needs at least ${MIN_PERSONAS} personas — with fewer than that you are running an interview, not a group.`;
  }
  if (setup.personaIds.length > MAX_PERSONAS) {
    return `A room holds at most ${MAX_PERSONAS} personas.`;
  }
  if (!Number.isInteger(setup.rounds) || setup.rounds < 1 || setup.rounds > MAX_ROUNDS) {
    return `Plan between 1 and ${MAX_ROUNDS} questions for the room.`;
  }
  if (!setup.model) {
    return "Choose a model from the curated catalog.";
  }
  // Persona count never unlocks an expensive model; only the checkbox does.
  if (!isInterviewModelSelectable(setup.model, setup.expensiveOptIn)) {
    return "Expensive models require the opt-in checkbox for this room.";
  }
  return null;
}

export function canStartFocusGroup(setup: Parameters<typeof focusGroupSetupRefusal>[0]) {
  return focusGroupSetupRefusal(setup) === null;
}

/** Stages reached so far, plus the next one. Nothing further: no skipping the funnel. */
export function selectableStages(room: Pick<FocusGroupRoom, "stages_reached"> | null) {
  const reached = room?.stages_reached ?? [];
  const furthest = reached.reduce(
    (max, stage) => Math.max(max, FOCUS_GROUP_STAGES.indexOf(stage)),
    -1
  );
  return FOCUS_GROUP_STAGES.slice(0, Math.min(furthest + 2, FOCUS_GROUP_STAGES.length));
}

export function canAskStage(room: Pick<FocusGroupRoom, "stages_reached"> | null, stage: FocusGroupStage) {
  return selectableStages(room).includes(stage);
}

/** Answers collected so far, whatever the room's status — going back never drops them. */
export function collectedAnswers(room: Pick<FocusGroupRoom, "rounds"> | null) {
  return (room?.rounds ?? []).flatMap((round) =>
    round.answers.filter((answer) => answer.status === "answered")
  );
}

export function missingAnswers(room: Pick<FocusGroupRoom, "rounds"> | null) {
  return (room?.rounds ?? []).flatMap((round) =>
    round.answers
      .filter((answer) => answer.status === "missing")
      .map((answer) => ({ round: round.index, persona_id: answer.persona_id }))
  );
}

export function focusGroupPath(roomId?: string, suffix?: string) {
  const base = "focus-group/rooms";
  if (!roomId) return base;
  return suffix ? `${base}/${encodeURIComponent(roomId)}/${suffix}` : `${base}/${encodeURIComponent(roomId)}`;
}

// --- the student's own memo (Fix 5) -----------------------------------------

export type ManualQuote = { turn_id: string; text: string };
export type ManualMemo = {
  /** Server-assigned; a save must name the version it was edited from. */
  version?: number;
  themes: { label: string; synthesis: string; quotes: ManualQuote[] }[];
  surprise: { summary: string; quote: ManualQuote };
  answer_options: { text: string; topic: string; turn_id: string }[];
  moderation_improvement: string;
};
export type QuoteTarget = `theme-${number}` | "surprise";

const MEMO_THEMES = 3;
const MEMO_OPTIONS = 3;

/** A saved draft, padded to the three themes and three options the memo needs. */
export function manualMemoFrom(saved?: ManualMemo | null): ManualMemo {
  const themes = [...(saved?.themes ?? [])];
  while (themes.length < MEMO_THEMES) themes.push({ label: "", synthesis: "", quotes: [] });
  const options = [...(saved?.answer_options ?? [])];
  while (options.length < MEMO_OPTIONS) options.push({ text: "", topic: "", turn_id: "" });
  return {
    themes,
    surprise: saved?.surprise ?? { summary: "", quote: { turn_id: "", text: "" } },
    answer_options: options,
    moderation_improvement: saved?.moderation_improvement ?? "",
  };
}

/** Answered turns only: a quote can only come from something a participant said. */
export function quotableTurns(room: Pick<FocusGroupRoom, "rounds"> | null) {
  return (room?.rounds ?? []).flatMap((round) =>
    round.answers
      .filter((answer) => answer.status === "answered" && answer.turn_id)
      .map((answer) => ({ turn_id: answer.turn_id as string, persona_id: answer.persona_id, text: answer.text }))
  );
}

/** Cite a whole turn; the student trims the words in the form afterwards. */
export function addQuote(memo: ManualMemo, target: QuoteTarget, turn: { turn_id: string; text: string }) {
  const quote = { turn_id: turn.turn_id, text: turn.text };
  if (target === "surprise") return { ...memo, surprise: { ...memo.surprise, quote } };
  const index = Number(target.slice("theme-".length));
  return {
    ...memo,
    themes: memo.themes.map((theme, n) => (n === index ? { ...theme, quotes: [...theme.quotes, quote] } : theme)),
  };
}

/** The retry control has to say it costs money again, and what the failure already cost. */
export function aiMemoRetryLabel(memo: Pick<FocusGroupMemo, "estimated_cost_usd" | "saved">) {
  const estimate = formatFocusGroupCostEstimate(Number(memo.estimated_cost_usd));
  if (!memo.saved || memo.saved.themes) return `Confirm ${estimate} and write it`;
  const already =
    memo.saved.outcome === "charged" && memo.saved.cost_usd
      ? `the failed attempt was charged $${Number(memo.saved.cost_usd).toFixed(4)}`
      : "the failed attempt's charge is unknown";
  return `Retry the AI draft — a new charge of about ${estimate} (${already})`;
}

// --- the concept card and what participants have been shown (Fix 2) ---------

export type RevealKind = "concept" | "price";
export type ConceptCard = {
  name: string;
  description: string;
  specs: string[];
  intended_for: string;
  introduction: string;
  /** The plain-text stimulus participants receive, and what "Copy" puts on the clipboard. */
  text: string;
  /** Visible to the moderator only; withheld from participants until Reveal price. */
  price: string;
};
export type SharedStimulus = { kind: RevealKind; round: number; turn_id: string; stage: FocusGroupStage; text: string };

type RevealRoom = Pick<FocusGroupRoom, "rounds">;

const stageIndex = (stage: FocusGroupStage) => FOCUS_GROUP_STAGES.indexOf(stage);

function shownKinds(room: RevealRoom | null) {
  return new Set((room?.rounds ?? []).flatMap((round) => (round.stimulus ? [round.stimulus.kind] : [])));
}

/** Why a reveal is not available yet, or null when it is. Mirrors _check_reveal in focus_group.py. */
export function revealRefusal(room: RevealRoom | null, stage: FocusGroupStage, kind: RevealKind): string | null {
  const shown = shownKinds(room);
  if (shown.has(kind)) return `The ${kind} has already been shown to this room.`;
  if (kind === "concept") {
    return stageIndex(stage) < stageIndex("concept") ? "Introduce the concept at the concept stage." : null;
  }
  if (!shown.has("concept")) return "Introduce the concept before revealing its price.";
  if (stageIndex(stage) < stageIndex("price_reactions")) return "Reveal the price at the price-reactions stage.";
  const unaided = (room?.rounds ?? []).some(
    (round) => round.stage === "price_reactions" && round.answers.some((answer) => answer.status === "answered")
  );
  return unaided ? null : "Ask the unaided price question first, then reveal the price.";
}

/** One line per thing the room has been told, in order — plus what it has not. */
export function sharedSummary(room: RevealRoom | null) {
  const shown = (room?.rounds ?? [])
    .filter((round) => round.stimulus)
    .map((round) => ({
      kind: round.stimulus!.kind,
      line: `Before question ${round.index + 1} (${FOCUS_GROUP_STAGE_LABELS[round.stage]}): ${
        round.stimulus!.kind === "concept" ? "the concept card" : "the price"
      }`,
      text: round.stimulus!.text,
    }));
  const kinds = new Set(shown.map((entry) => entry.kind));
  const withheld = (["concept", "price"] as RevealKind[])
    .filter((kind) => !kinds.has(kind))
    .map((kind) => (kind === "concept" ? "Not shown yet: the concept card" : "Not shown yet: the price"));
  return { shown, withheld };
}

// --- persona cards (Fix 1) ----------------------------------------------------

export type CardSource = "census" | "fictional" | "unknown";
export type PersonaCard = {
  persona_id: string;
  name: string;
  origin: "source_grounded_roster" | "student_created";
  origin_label: string;
  attributes: { key: string; label: string; value: string; source: CardSource }[];
  screener: { criterion: string; verdict: "meets" | "does_not_meet" | "unknown"; why: string; source: CardSource }[];
  source_note: string;
  version?: number;
  based_on?: string | null;
};

export const CARD_SOURCE_LABELS: Record<CardSource, string> = {
  census: "Source-backed (ACS)",
  fictional: "Fictional",
  unknown: "Unknown",
};

export const SCREENER_VERDICT_LABELS = {
  meets: "Meets",
  does_not_meet: "Does not meet",
  unknown: "Can't tell from the profile",
} as const;

/** The one line a closed card shows: who, and where they stand on the screener. */
export function cardHeadline(card: PersonaCard) {
  const counts = { meets: 0, does_not_meet: 0, unknown: 0 };
  for (const entry of card.screener) counts[entry.verdict] += 1;
  const who = card.name ? `${card.persona_id} · ${card.name}` : card.persona_id;
  return `${who} — screener: ${counts.meets} meet, ${counts.does_not_meet} do not, ${counts.unknown} unknown`;
}

// --- asking: recipients, core vs probe, the allowance (Fix 4) -------------------

export type Allowance = {
  total: number;
  used: number;
  cores_total: number;
  cores_left: number;
  probes_used: number;
  probes_left: number;
  extensions_left: number;
};

/** The first question at a stage is its core question; every later one is a follow-up probe. */
/** Mirrors ask_round: a question at the concept stage or later is the stage's core question
 * only once the concept is on screen (shown before, or introduced with it). */
export function questionKind(
  room: Pick<FocusGroupRoom, "rounds"> | null,
  stage: FocusGroupStage,
  reveal: RevealKind | null = null
) {
  const at = (s: FocusGroupStage) => FOCUS_GROUP_STAGES.indexOf(s);
  let conceptShown = false;
  const counted = new Set<FocusGroupStage>();
  for (const round of room?.rounds ?? []) {
    conceptShown ||= round.stimulus?.kind === "concept";
    if (conceptShown || at(round.stage) < at("concept")) counted.add(round.stage);
  }
  const counts = at(stage) < at("concept") || conceptShown || reveal === "concept";
  return counts && !counted.has(stage) ? "core" : "probe";
}

/** True when the form differs from the saved memo — only then does Export save it first,
 * so an untouched form never becomes a blank "draft" and a stale tab has nothing to push. */
export function manualMemoEdited(saved: ManualMemo | null | undefined, current: ManualMemo) {
  return JSON.stringify(manualMemoFrom(saved)) !== JSON.stringify(manualMemoFrom(current));
}

export function nextStage(stage: FocusGroupStage): FocusGroupStage | null {
  return FOCUS_GROUP_STAGES[FOCUS_GROUP_STAGES.indexOf(stage) + 1] ?? null;
}

export function allowanceLine(allowance: Allowance | undefined) {
  if (!allowance) return "";
  return (
    `Core questions left: ${allowance.cores_left} of ${allowance.cores_total} · ` +
    `Follow-up probes left: ${allowance.probes_left} (used ${allowance.probes_used})`
  );
}

/** Why Ask is refusing, in the student's words, or null. Mirrors ask_round's checks. */
export function askRefusal(
  room: Pick<FocusGroupRoom, "rounds" | "allowance"> | null,
  stage: FocusGroupStage,
  target: { mode: "room" | "selected"; selected: string[] },
  reveal: RevealKind | null = null
) {
  if (target.mode === "selected" && target.selected.length === 0) {
    return "Choose at least one participant, or ask the whole room.";
  }
  const allowance = room?.allowance;
  if (!allowance) return null;
  if (allowance.used >= allowance.total) return "This room has used all the questions it was started with.";
  if (questionKind(room, stage, reveal) === "probe" && allowance.probes_left <= 0) {
    return "No follow-up probes left — move to the next stage, or extend the room for more probes.";
  }
  return null;
}

/** What an unanswered turn says inside the dialogue. Never the provider's technical text:
 * that belongs in the alert above the transcript, not in a participant's mouth. */
export function unansweredNote(answer: Pick<FocusGroupAnswer, "status" | "error">) {
  if (answer.status === "silent") return "not asked — intentionally silent";
  if (answer.error?.code === "out_of_character") return "reply withheld (it stepped out of character) — retry below";
  return answer.error ? "no answer — retry below" : "not run yet";
}

// --- student-created practice personas (Fix 3) ------------------------------------

export type PersonaFields = {
  name: string;
  household: string;
  tenure: "owner" | "landowner" | "renter" | "lives_with_family" | "unknown";
  outdoor_space: "yes" | "no" | "unknown";
  outdoor_note: string;
  current_space_use: string;
  willing_more_space: "yes" | "maybe" | "no" | "unknown";
  constraints: string;
  style: "" | "brief" | "talkative";
  research_link: string;
};
export type StudentPersona = {
  id: string;
  persona_id: string;
  version: number;
  based_on: string | null;
  fields: PersonaFields;
  card: PersonaCard;
  description: string;
};

export function emptyPersonaFields(): PersonaFields {
  return {
    name: "",
    household: "",
    tenure: "unknown",
    outdoor_space: "unknown",
    outdoor_note: "",
    current_space_use: "",
    willing_more_space: "unknown",
    constraints: "",
    style: "",
    research_link: "",
  };
}

/** Duplicate and edit: start from what a roster card actually says; unknowns stay unknown. */
export function fieldsFromRosterCard(card: PersonaCard): PersonaFields {
  const value = (key: string) => {
    const attribute = card.attributes.find((entry) => entry.key === key);
    return attribute && attribute.source !== "unknown" ? attribute.value : "";
  };
  const tenure = value("tenure").toLowerCase();
  return {
    ...emptyPersonaFields(),
    household: [value("household"), value("age"), value("county")].filter(Boolean).join("; "),
    tenure: tenure.startsWith("own") ? "owner" : tenure.startsWith("rent") ? "renter" : "unknown",
    constraints: value("housing_cost") ? `Housing costs take ${value("housing_cost")} of income` : "",
  };
}

/** Mirrors clean_fields' required fields, so Save explains itself before the round trip. */
export function personaFormRefusal(fields: PersonaFields) {
  if (!fields.household.trim()) return "Describe the household and living situation.";
  if (!fields.research_link.trim()) return "Say how this profile relates to your research question.";
  return null;
}

// --- the student's product photo --------------------------------------------
// ponytail: the image stays in the browser (an object URL), never uploaded; lost on reload.
// Personas are text models, so only the student's description travels, with the concept.

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
export const PHOTO_CAPTION_MAX = 500;
export type ConceptPhoto = { roomId: string; filename: string; url: string; caption: string };

export function photoFileRefusal(file: { type: string; size: number }) {
  if (!PHOTO_TYPES.includes(file.type)) return "Choose a JPEG, PNG, WebP or GIF image.";
  if (file.size > PHOTO_MAX_BYTES) return "That photo is over 5 MB. Choose a smaller one.";
  return null;
}

/** What the ask request carries about the photo: filename and description only, and only
 * with the concept introduction. Never the image or its URL. */
export function photoForAsk(photo: ConceptPhoto | null, reveal: RevealKind | null) {
  if (!photo || reveal !== "concept") return {};
  return { photo: { filename: photo.filename, caption: photo.caption.trim() } };
}

export function cardTextWithPhoto(text: string, photo: ConceptPhoto | null) {
  const caption = photo?.caption.trim();
  return caption ? `${text}\nPhoto the moderator is showing (described in words): ${caption}` : text;
}
