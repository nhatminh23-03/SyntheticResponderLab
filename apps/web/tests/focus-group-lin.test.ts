import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  addQuote,
  aiMemoRetryLabel,
  cardTextWithPhoto,
  PHOTO_CAPTION_MAX,
  PHOTO_MAX_BYTES,
  photoFileRefusal,
  photoForAsk,
  manualMemoEdited,
  manualMemoFrom,
  quotableTurns,
  REHEARSAL_LABEL,
  type FocusGroupStage,
} from "../src/lib/focus-group";

const read = (path: string) => readFileSync(resolve(__dirname, "../..", path), "utf8");
const pageSource = read("src/app/focus-group/page.tsx");
const memoFormSource = read("src/components/focus-group/manual-memo-form.tsx");
const apiSource = readFileSync(resolve(__dirname, "../../../api/src/services/focus_group.py"), "utf8");

const ROOM = {
  rounds: [
    {
      index: 0,
      stage: "icebreaker" as FocusGroupStage,
      question: "q",
      answers: [
        { turn_id: "R1-P001", persona_id: "P001", text: "I use the garage.", status: "answered" as const, error: null },
        { turn_id: "R1-P002", persona_id: "P002", text: "", status: "missing" as const, error: null },
      ],
    },
  ],
};

// --- Fix 5 ------------------------------------------------------------------

test("rehearsal label: the page and the API carry the same words", () => {
  assert.equal(REHEARSAL_LABEL, "Synthetic rehearsal - not PA3.5 live fieldwork");
  assert.match(apiSource, /REHEARSAL_LABEL = "Synthetic rehearsal - not PA3\.5 live fieldwork"/);
  assert.match(pageSource, /\{REHEARSAL_LABEL\}/);
});

test("manual memo: a saved draft is restored, padded to three themes and three options", () => {
  const empty = manualMemoFrom(null);
  assert.equal(empty.themes.length, 3);
  assert.equal(empty.answer_options.length, 3);
  const restored = manualMemoFrom({
    themes: [{ label: "Cold garage", synthesis: "", quotes: [] }],
    surprise: { summary: "s", quote: { turn_id: "R1-P001", text: "garage" } },
    answer_options: [],
    moderation_improvement: "m",
  });
  assert.equal(restored.themes[0].label, "Cold garage");
  assert.equal(restored.themes.length, 3);
  assert.equal(restored.surprise.quote.turn_id, "R1-P001");
  // Re-opening, starting, and opening a demo all restore the saved draft.
  assert.equal((pageSource.match(/setManualMemo\(manualMemoFrom\(result\.room\.manual_memo\)\)/g) ?? []).length, 3);
});

test("manual memo: only answered turns are quotable, and a quote keeps its turn ID", () => {
  assert.deepEqual(quotableTurns(ROOM).map((t) => t.turn_id), ["R1-P001"]);
  const memo = addQuote(manualMemoFrom(null), "theme-1", quotableTurns(ROOM)[0]);
  assert.deepEqual(memo.themes[1].quotes, [{ turn_id: "R1-P001", text: "I use the garage." }]);
  assert.equal(addQuote(memo, "surprise", quotableTurns(ROOM)[0]).surprise.quote.turn_id, "R1-P001");
});

test("manual memo: the form comes before the optional AI draft and each turn shows its ID and a Quote control", () => {
  assert.ok(pageSource.indexOf("<ManualMemoForm") < pageSource.indexOf("Optional: AI draft memo"));
  assert.match(pageSource, /\[\{answer\.turn_id\}\]/);
  assert.match(pageSource, /aria-label=\{`Quote \$\{answer\.turn_id\} in your memo`\}/);
  assert.match(memoFormSource, /PA4 answer options/);
  assert.match(memoFormSource, /question topic/);
  assert.match(memoFormSource, /would change about how you moderated/);
  // Exporting saves unsaved on-screen edits first, so typed work is never left out of the file.
  assert.match(pageSource, /\(edited \? postManualMemo\(\) : Promise\.resolve\(\)\)\s*\.catch\([\s\S]*?\.then\(\(\) =>\s*interviewOperation/,
    "a failed memo save never blocks the export");
});

test("manual memo: a failed AI attempt's retry says it is a new charge and what the failure cost", () => {
  const label = aiMemoRetryLabel({
    estimated_cost_usd: "0.0021",
    saved: { attempt: 1, outcome: "charged", cost_usd: "0.002", themes: null },
  });
  assert.match(label, /new charge of about \$0\.002/);
  assert.match(label, /failed attempt was charged \$0\.0020/);
  assert.match(aiMemoRetryLabel({ estimated_cost_usd: "0.0021", saved: null }), /Confirm \$0\.002 and write it/);
});

// --- the classroom allowlist: every new student endpoint, nothing wider ---------

import { isClassroomInterviewApiRequest } from "../src/lib/classroom-access";

const ROOMS = "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms";
const NEW_STUDENT_ENDPOINTS: [string, string][] = [
  ["POST", `${ROOMS}/fg_1/manual-memo`],
  ["POST", `${ROOMS}/fg_1/extend`],
  ["GET", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas"],
  ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas"],
  ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas/fgp_abc"],
];
const STILL_REFUSED: [string, string][] = [
  ["GET", `${ROOMS}/fg_1/manual-memo`],
  ["DELETE", `${ROOMS}/fg_1/manual-memo`],
  ["POST", `${ROOMS}/fg_1/manual-memo/extra`],
  ["POST", `${ROOMS}/fg_1/manual-memo%2F..%2F..`],
  ["POST", `${ROOMS}/fg_1/manual`],
  ["GET", `${ROOMS}/fg_1/extend`],
  ["POST", `${ROOMS}/fg_1/extend/more`],
  ["DELETE", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas/fgp_abc"],
  ["GET", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas/fgp_abc"],
  ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas/fgp_abc/rooms"],
  ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas/..%2F..%2Fsimulation-runs"],
  ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/personas-all"],
];

test("classroom allowlist: every new student endpoint is reachable and nothing wider opened", () => {
  for (const [method, path] of NEW_STUDENT_ENDPOINTS) {
    assert.equal(isClassroomInterviewApiRequest(path, method), true, `${method} ${path}`);
  }
  for (const [method, path] of STILL_REFUSED) {
    assert.equal(isClassroomInterviewApiRequest(path, method), false, `${method} ${path}`);
  }
});

// --- Fix 2 ------------------------------------------------------------------

import { revealRefusal, sharedSummary } from "../src/lib/focus-group";

const conceptCardSource = read("src/components/focus-group/concept-card.tsx");

function roundAt(index: number, stage: FocusGroupStage, stimulus?: "concept" | "price") {
  return {
    index,
    stage,
    question: "q",
    ...(stimulus ? { stimulus: { kind: stimulus, text: `${stimulus} text` } } : {}),
    answers: [{ persona_id: "P001", text: "a", status: "answered" as const, error: null }],
  };
}

test("concept card: it sits directly above the question field and can be copied as text", () => {
  const card = pageSource.indexOf("<ConceptCardPanel");
  const input = pageSource.indexOf("value={question}");
  assert.ok(card > 0 && card < input, "the card renders before the question input");
  assert.equal(pageSource.slice(card, input).includes("<ol"), false, "nothing but the card sits between them");
  assert.match(conceptCardSource, /navigator\.clipboard\?\.writeText\(cardTextWithPhoto\(card\.text, photo\)\)/);
  assert.match(conceptCardSource, /Introduction you read aloud \(edit freely\)/);
  assert.match(conceptCardSource, /card\.specs\.map/);
  // The page sends the reveal with the question; nothing is revealed on its own.
  assert.match(pageSource, /reveal: pendingReveal/);
});

test("concept card: Reveal price waits for the concept and an unaided price answer", () => {
  assert.match(String(revealRefusal({ rounds: [] }, "icebreaker", "concept")), /concept stage/);
  assert.equal(revealRefusal({ rounds: [] }, "concept", "concept"), null);
  const introduced = { rounds: [roundAt(0, "concept", "concept")] };
  assert.match(String(revealRefusal(introduced, "concept", "concept")), /already been shown/);
  assert.match(String(revealRefusal(introduced, "price_reactions", "price")), /unaided price question first/);
  const unaided = { rounds: [...introduced.rounds, roundAt(1, "price_reactions")] };
  assert.equal(revealRefusal(unaided, "price_reactions", "price"), null);
  assert.match(String(revealRefusal({ rounds: [roundAt(0, "price_reactions")] }, "price_reactions", "price")), /concept before/);
  assert.match(conceptCardSource, /disabled=\{busy \|\| priceRefusal !== null\}[\s\S]*?Reveal price/);
});

test("shared with participants: the panel lists each stimulus with its question, and what is withheld", () => {
  const none = sharedSummary({ rounds: [roundAt(0, "icebreaker")] });
  assert.deepEqual(none.shown, []);
  assert.deepEqual(none.withheld, ["Not shown yet: the concept card", "Not shown yet: the price"]);
  const some = sharedSummary({ rounds: [roundAt(0, "icebreaker"), roundAt(1, "concept", "concept")] });
  assert.equal(some.shown[0].line, "Before question 2 (The Tahoe Mini concept): the concept card");
  assert.equal(some.shown[0].text, "concept text");
  assert.deepEqual(some.withheld, ["Not shown yet: the price"]);
  assert.match(conceptCardSource, /Information shared with participants/);
});

// --- Fix 1 ------------------------------------------------------------------

import { CARD_SOURCE_LABELS, cardHeadline, type PersonaCard } from "../src/lib/focus-group";

const personaCardSource = read("src/components/focus-group/persona-card.tsx");
const CARD: PersonaCard = {
  persona_id: "P001",
  name: "Jorge Beltran",
  origin: "source_grounded_roster",
  origin_label: "Roster persona",
  attributes: [
    { key: "tenure", label: "Homeowner or renter", value: "Owned free and clear", source: "census" },
    { key: "outdoor_space", label: "Usable outdoor space", value: "Unknown", source: "unknown" },
  ],
  screener: [
    { criterion: "Homeowner or landowner", verdict: "meets", why: "Owned", source: "census" },
    { criterion: "Has usable outdoor space", verdict: "unknown", why: "Not recorded", source: "unknown" },
  ],
  source_note: "note",
};

test("persona card: recruitment shows an expandable card per persona, with each attribute's source", () => {
  assert.match(pageSource, /personas\.map\(\(persona\) => \([\s\S]*?Recruit \{persona\.persona_id\}[\s\S]*?<PersonaCardView\s+card=\{persona\.card\}/);
  assert.match(personaCardSource, /<details/);
  assert.match(personaCardSource, /CARD_SOURCE_LABELS\[attribute\.source\]/);
  assert.match(personaCardSource, /SCREENER_VERDICT_LABELS\[entry\.verdict\]/);
  assert.deepEqual(CARD_SOURCE_LABELS, { census: "Source-backed (ACS)", fictional: "Fictional", unknown: "Unknown" });
  assert.equal(cardHeadline(CARD), "P001 · Jorge Beltran — screener: 1 meet, 0 do not, 1 unknown");
  // The old ID-only chip is gone.
  assert.doesNotMatch(pageSource, /aria-pressed=\{selectedPersonaIds/);
});

test("persona card: the seated participants' cards stay beside the discussion", () => {
  assert.match(pageSource, /<aside aria-label="Who is in the room"[\s\S]*?room\.participants[\s\S]*?<PersonaCardView/);
});

// --- Fix 4 ------------------------------------------------------------------

import {
  allowanceLine,
  askRefusal,
  missingAnswers,
  nextStage,
  questionKind,
  unansweredNote,
} from "../src/lib/focus-group";

const ALLOWANCE = { total: 8, used: 3, cores_total: 5, cores_left: 3, probes_used: 1, probes_left: 2, extensions_left: 4 };

test("recipient selector: whole room or selected participants, silence is not an error", () => {
  assert.match(pageSource, /Whole room[\s\S]*?Selected participant\(s\)/);
  assert.match(pageSource, /recipients: target\.selected/);
  assert.match(String(askRefusal(null, "icebreaker", { mode: "selected", selected: [] })), /at least one participant/);
  assert.equal(askRefusal(null, "icebreaker", { mode: "selected", selected: ["P002"] }), null);
  const room = {
    rounds: [
      {
        index: 0,
        stage: "icebreaker" as FocusGroupStage,
        question: "q",
        recipients: ["P002"],
        answers: [
          { persona_id: "P001", text: "", status: "silent" as const, error: null },
          { persona_id: "P002", text: "a", status: "answered" as const, error: null },
        ],
      },
    ],
  };
  assert.deepEqual(missingAnswers(room), [], "silent is never a missing answer");
  assert.equal(unansweredNote({ status: "silent", error: null }), "not asked — intentionally silent");
  // Technical provider text never lands in the dialogue.
  assert.equal(unansweredNote({ status: "missing", error: { code: "provider_unavailable", message: "HTTP 502 upstream" } }), "no answer — retry below");
  assert.match(unansweredNote({ status: "missing", error: { code: "out_of_character", message: "x" } }), /out of character/);
  assert.doesNotMatch(pageSource, /answer\.error\?\.message/);
  assert.match(pageSource, /answer\.status !== "silent"/);
});

test("recipient selector: Ask follow-up and Next stage are separate, stage buttons stay, allowance shows", () => {
  const room = { rounds: [{ index: 0, stage: "icebreaker" as FocusGroupStage, question: "q", answers: [] }], allowance: ALLOWANCE };
  assert.equal(questionKind(room, "icebreaker"), "probe");
  assert.equal(questionKind(room, "space_needs"), "core");
  assert.equal(nextStage("price_reactions"), "close");
  assert.equal(nextStage("close"), null);
  assert.equal(allowanceLine(ALLOWANCE), "Core questions left: 3 of 5 · Follow-up probes left: 2 (used 1)");
  assert.match(String(askRefusal({ ...room, allowance: { ...ALLOWANCE, probes_left: 0 } }, "icebreaker", { mode: "room", selected: [] })), /extend the room/);
  assert.equal(askRefusal({ ...room, allowance: { ...ALLOWANCE, probes_left: 0 } }, "space_needs", { mode: "room", selected: [] }), null, "a core question is never blocked by probes");
  assert.match(pageSource, /"Ask follow-up"[\s\S]*?"Ask core question"/);
  assert.match(pageSource, /Next stage: \$\{FOCUS_GROUP_STAGE_LABELS\[nextStage\(stage\)!\]\} →/);
  assert.match(pageSource, /FOCUS_GROUP_STAGES\.map\(\(entry, index\) => \(/, "manual stage buttons remain");
  assert.match(pageSource, /\{allowanceLine\(room\.allowance\)\}/);
  assert.match(pageSource, /aria-label="Confirm extension cost"[\s\S]*?Confirm and extend/);
  assert.match(pageSource, /extra_rounds: extendBy,\s*authorize_charge: true/);
});

// --- Fix 3 ------------------------------------------------------------------

import { emptyPersonaFields, fieldsFromRosterCard, personaFormRefusal } from "../src/lib/focus-group";

const personaFormSource = read("src/components/focus-group/persona-form.tsx");

test("create persona: Create and Duplicate and edit sit beside the roster, preview comes before save", () => {
  assert.match(pageSource, /Duplicate and edit/);
  assert.match(pageSource, /Create persona/);
  assert.match(pageSource, /preview: true/);
  assert.match(personaFormSource, /disabled=\{busy \|\| refusal !== null \|\| !preview\}/, "Save waits for a preview");
  assert.match(pageSource, /setPersonaPreview\(null\); \/\/ a preview must show what will actually be saved/);
  assert.match(personaFormSource, /Student-created fictional persona/);
  assert.match(personaFormSource, /never counts as\s+recruiting a real PA3\.5 participant/);
  for (const label of ["Household and living situation", "Tenure", "Usable outdoor space",
    "How they use their space today", "Willing to consider additional living or work space",
    "Relevant constraints", "Conversation style", "relate to your research question"]) {
    assert.ok(personaFormSource.includes(label), label);
  }
  assert.doesNotMatch(personaFormSource, /opinion|desired finding/i, "no predetermined opinion or findings field");
});

test("create persona: duplicating copies what the roster card says and nothing it does not", () => {
  const copy = fieldsFromRosterCard({
    ...CARD,
    attributes: [
      ...CARD.attributes,
      { key: "household", label: "Household", value: "Married couple household, 4 people", source: "census" },
    ],
  });
  assert.equal(copy.tenure, "owner");
  assert.equal(copy.outdoor_space, "unknown", "an unknown stays unknown");
  assert.match(copy.household, /Married couple household/);
  assert.equal(copy.research_link, "");
  assert.match(String(personaFormRefusal(emptyPersonaFields())), /household/);
  assert.match(String(personaFormRefusal({ ...emptyPersonaFields(), household: "x" })), /research question/);
});

// --- refuter round ------------------------------------------------------------------------

test("memo lost update: export saves only an edited memo, on top of the version it loaded", () => {
  const saved = { ...manualMemoFrom(null), version: 3 };
  assert.equal(manualMemoEdited(null, manualMemoFrom(null)), false, "an untouched form is not a memo");
  assert.equal(manualMemoEdited(saved, manualMemoFrom(saved)), false);
  const edited = manualMemoFrom(saved);
  edited.moderation_improvement = "Ask P003 sooner.";
  assert.equal(manualMemoEdited(saved, edited), true);
  assert.match(pageSource, /base_version: room!\.manual_memo\?\.version \?\? 0/);
  assert.match(pageSource, /\(edited \? postManualMemo\(\) : Promise\.resolve\(\)\)/);
});

test("concept stage: a question without the concept on screen is a probe, not the stage's core", () => {
  const rounds = (["icebreaker", "space_needs"] as FocusGroupStage[]).map((stage, index) => ({ index, stage, question: "q", answers: [] }));
  assert.equal(questionKind({ rounds }, "concept"), "probe");
  assert.equal(questionKind({ rounds }, "concept", "concept"), "core");
  const legacy = [...rounds, { index: 2, stage: "concept" as FocusGroupStage, question: "q", answers: [],
    stimulus: { kind: "concept" as const, text: "t", derived: true } }];
  assert.equal(questionKind({ rounds: legacy }, "price_reactions"), "core");
  assert.match(String(askRefusal({ rounds, allowance: { ...ALLOWANCE, probes_left: 0 } }, "concept", { mode: "room", selected: [] })), /probes/);
  assert.equal(askRefusal({ rounds, allowance: { ...ALLOWANCE, probes_left: 0 } }, "concept", { mode: "room", selected: [] }, "concept"), null);
});

test("extension: a refused (stale) extension surfaces its message instead of looking like success", () => {
  const extend = pageSource.slice(pageSource.indexOf("async function extendRoom"), pageSource.indexOf("async function openRoom"));
  assert.match(extend, /await run\(/, "run() shows the server's 409 message in the alert");
  assert.match(extend, /if \(result\) setRoom\(result\.room\)/, "only a real extension updates the room");
});

// --- the student's product photo -------------------------------------------

test("photo: file rules accept jpeg/png/webp/gif up to 5 MB and refuse the rest", () => {
  for (const type of ["image/jpeg", "image/png", "image/webp", "image/gif"]) {
    assert.equal(photoFileRefusal({ type, size: PHOTO_MAX_BYTES }), null);
  }
  assert.match(photoFileRefusal({ type: "image/png", size: PHOTO_MAX_BYTES + 1 })!, /over 5 MB/);
  for (const type of ["application/pdf", "image/svg+xml", "text/plain", ""]) {
    assert.match(photoFileRefusal({ type, size: 10 })!, /JPEG, PNG, WebP or GIF/);
  }
});

test("photo: the ask request carries only filename and description, never the image", () => {
  const photo = { roomId: "r", filename: "tahoe.jpg", url: "blob:http://x/abc", caption: " Cedar cabin. " };
  const body = JSON.stringify({ revision: 1, question: "q", reveal: "concept", ...photoForAsk(photo, "concept") });
  assert.deepEqual(JSON.parse(body).photo, { filename: "tahoe.jpg", caption: "Cedar cabin." });
  assert.doesNotMatch(body, /blob:|data:|base64/);
  assert.deepEqual(photoForAsk(photo, null), {});
  assert.deepEqual(photoForAsk(photo, "price"), {});
  assert.deepEqual(photoForAsk(null, "concept"), {});
  // The page spreads photoForAsk into the ask body and posts the file nowhere.
  assert.match(pageSource, /photoForAsk\(roomPhoto, pendingReveal\)/);
  for (const source of [pageSource, conceptCardSource]) {
    assert.doesNotMatch(source, /FormData|readAsDataURL|readAsArrayBuffer|\.arrayBuffer\(|localStorage/);
  }
  assert.doesNotMatch(conceptCardSource, /fetch\(|interviewOperation/);
});

test("photo: the card offers add/replace/remove, says participants only get the description, copies it", () => {
  assert.match(conceptCardSource, /Add a product photo/);
  assert.match(conceptCardSource, /Replace photo/);
  assert.match(conceptCardSource, /Remove photo/);
  assert.match(conceptCardSource, /Participants can&apos;t see images\. They only get this description, and only after you\s+introduce the concept\./);
  assert.match(conceptCardSource, /maxLength=\{PHOTO_CAPTION_MAX\}/);
  assert.equal(PHOTO_CAPTION_MAX, 500);
  assert.match(conceptCardSource, /URL\.createObjectURL/);
  assert.match(pageSource, /URL\.revokeObjectURL\(photoUrl\)/);
  assert.match(conceptCardSource, /cardTextWithPhoto\(card\.text, photo\)/);
  const photo = { roomId: "r", filename: "t.jpg", url: "blob:x", caption: "Cedar cabin." };
  assert.equal(cardTextWithPhoto("CARD", photo), "CARD\nPhoto the moderator is showing (described in words): Cedar cabin.");
  assert.equal(cardTextWithPhoto("CARD", null), "CARD");
  assert.equal(cardTextWithPhoto("CARD", { ...photo, caption: " " }), "CARD");
  // The same sentence the server adds to the participants' stimulus.
  assert.match(apiSource, /Photo the moderator is showing \(described in words\): /);
});
