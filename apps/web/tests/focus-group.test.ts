import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  canAskStage,
  collectedAnswers,
  estimateFocusGroupCost,
  FOCUS_GROUP_STAGES,
  FOCUS_GROUP_STAGE_LABELS,
  focusGroupSetupRefusal,
  formatFocusGroupCostEstimate,
  MAX_PERSONAS,
  MAX_ROUNDS,
  MIN_PERSONAS,
  missingAnswers,
  selectableStages,
  type FocusGroupStage,
} from "../src/lib/focus-group";
import {
  isClassroomFocusGroupPage,
  isClassroomInterviewApiRequest,
  isClassroomStudentPage,
} from "../src/lib/classroom-access";

const pageSource = readFileSync(
  resolve(__dirname, "../../src/app/focus-group/page.tsx"),
  "utf8"
);
const middlewareSource = readFileSync(resolve(__dirname, "../../src/middleware.ts"), "utf8");
const endSessionSource = readFileSync(
  resolve(__dirname, "../../src/app/api/classroom/end-session/route.ts"),
  "utf8"
);

const CHEAP = {
  id: "openai/gpt-4o-mini",
  name: "GPT-4o mini",
  tier: "cheap" as const,
  prompt_price_per_million: 0.15,
  completion_price_per_million: 0.6,
  estimated_cost_per_persona_usd: 0.0027,
};
const EXPENSIVE = { ...CHEAP, id: "anthropic/claude-sonnet-4.5", tier: "expensive" as const };

function setup(over: Partial<Parameters<typeof focusGroupSetupRefusal>[0]> = {}) {
  return {
    personaIds: ["P001", "P002", "P003"],
    rounds: 5,
    model: CHEAP,
    expensiveOptIn: false,
    ...over,
  };
}

// --- the three-persona floor ------------------------------------------------

test("a focus group refuses two personas and says why", () => {
  assert.equal(focusGroupSetupRefusal(setup()), null);
  const refusal = focusGroupSetupRefusal(setup({ personaIds: ["P001", "P002"] }));
  assert.match(String(refusal), /at least 3 personas/);
  assert.match(String(refusal), /interview, not a group/);
  assert.equal(MIN_PERSONAS, 3);
});

test("the room refuses a duplicated persona and an oversized room before anything is spent", () => {
  assert.match(
    String(focusGroupSetupRefusal(setup({ personaIds: ["P001", "P001", "P002"] }))),
    /one seat/
  );
  const tooMany = Array.from({ length: MAX_PERSONAS + 1 }, (_, i) => `P${i}`);
  assert.match(String(focusGroupSetupRefusal(setup({ personaIds: tooMany }))), /at most 8/);
  assert.match(String(focusGroupSetupRefusal(setup({ rounds: MAX_ROUNDS + 1 }))), /between 1 and 12/);
  assert.match(String(focusGroupSetupRefusal(setup({ rounds: 0 }))), /between 1 and 12/);
});

// --- cost estimate ----------------------------------------------------------

test("the estimate is personas times rounds, not one call", () => {
  const perTurn = (0.15 * 2000 + 0.6 * 400) / 1_000_000;
  assert.equal(estimateFocusGroupCost(3, 5, CHEAP), perTurn * 15);
  assert.equal(estimateFocusGroupCost(3, 5, CHEAP), estimateFocusGroupCost(5, 3, CHEAP));
  assert.equal(estimateFocusGroupCost(3, 5, undefined), 0);
});

test("the estimate moves when persona count, rounds, or model change", () => {
  const base = estimateFocusGroupCost(3, 5, CHEAP);
  assert.ok(estimateFocusGroupCost(4, 5, CHEAP) > base);
  assert.ok(estimateFocusGroupCost(3, 6, CHEAP) > base);
  const pricier = { ...CHEAP, prompt_price_per_million: 3, completion_price_per_million: 15 };
  assert.ok(estimateFocusGroupCost(3, 5, pricier) > base);
  assert.equal(formatFocusGroupCostEstimate(base), `$${base.toFixed(3)}`);
});

test("the page recomputes the confirmed estimate from the live controls", () => {
  assert.match(
    pageSource,
    /const estimate = useMemo\([\s\S]*?estimateFocusGroupCost\(selectedPersonaIds\.length, plannedRounds, model\),[\s\S]*?\[selectedPersonaIds\.length, plannedRounds, model\]/
  );
  // Start opens the confirmation; only the confirmation calls the paid endpoint.
  assert.match(
    pageSource,
    /<Button onClick=\{\(\) => setConfirming\(true\)\} disabled=\{readOnly \|\| busy \|\| refusal !== null\}/
  );
  assert.match(
    pageSource,
    /role="dialog"[\s\S]*?Nothing is spent until\s*\n?\s*you confirm[\s\S]*?onClick=\{startRoom\}[\s\S]*?onClick=\{\(\) => setConfirming\(false\)\}/
  );
  // Dismissing starts nothing: Cancel only closes the dialog.
  assert.doesNotMatch(
    pageSource,
    /onClick=\{\(\) => \{\s*setConfirming\(false\);\s*startRoom\(\)/
  );
});

test("the pre-start refusal and the estimate are both shown to the student", () => {
  assert.match(pageSource, /\{refusal \? \([\s\S]*?role="alert"[\s\S]*?\{refusal\}/);
  assert.match(
    pageSource,
    /\{selectedPersonaIds\.length\} personas × \{plannedRounds\} questions =/
  );
});

// --- expensive models -------------------------------------------------------

test("persona count alone can never reach an expensive model", () => {
  assert.match(
    String(focusGroupSetupRefusal(setup({ model: EXPENSIVE }))),
    /opt-in checkbox/
  );
  assert.equal(focusGroupSetupRefusal(setup({ model: EXPENSIVE, expensiveOptIn: true })), null);
  const big = Array.from({ length: MAX_PERSONAS }, (_, i) => `P${i}`);
  assert.match(
    String(focusGroupSetupRefusal(setup({ personaIds: big, model: EXPENSIVE }))),
    /opt-in checkbox/
  );
});

test("the page keeps the expensive checkbox as the only way in", () => {
  assert.match(
    pageSource,
    /type="checkbox"[\s\S]*?checked=\{expensiveOptIn\}[\s\S]*?Allow expensive models for this room/
  );
  assert.match(
    pageSource,
    /\.filter\(\(entry\) => isInterviewModelSelectable\(entry, expensiveOptIn\)\)/
  );
  assert.match(
    pageSource,
    /if \(!expensiveOptIn\) \{[\s\S]*?resetExpensiveModelSelection\(models, current, defaultModelId\)/
  );
});

// --- the five stages --------------------------------------------------------

test("the funnel is the five PA3.5 stages in order", () => {
  assert.deepEqual(FOCUS_GROUP_STAGES, [
    "icebreaker",
    "space_needs",
    "concept",
    "price_reactions",
    "close",
  ]);
  assert.equal(FOCUS_GROUP_STAGE_LABELS.price_reactions, "Price reactions");
  assert.equal(FOCUS_GROUP_STAGES.indexOf("price_reactions"), 3);
});

test("stages open one at a time and stay open once reached", () => {
  assert.deepEqual(selectableStages(null), ["icebreaker"]);
  assert.deepEqual(selectableStages({ stages_reached: ["icebreaker"] }), [
    "icebreaker",
    "space_needs",
  ]);
  const midway = { stages_reached: ["icebreaker", "space_needs", "concept"] as FocusGroupStage[] };
  assert.equal(canAskStage(midway, "icebreaker"), true, "going back stays available");
  assert.equal(canAskStage(midway, "price_reactions"), true);
  assert.equal(canAskStage(midway, "close"), false, "the funnel cannot be skipped forward");
  assert.equal(canAskStage(null, "concept"), false);
});

test("going back to an earlier stage keeps every answer already collected", () => {
  const room = {
    rounds: [
      {
        index: 0,
        stage: "icebreaker" as FocusGroupStage,
        question: "q1",
        answers: [
          { persona_id: "P001", text: "a", status: "answered" as const, error: null },
          { persona_id: "P002", text: "", status: "missing" as const, error: null },
        ],
      },
      {
        index: 1,
        stage: "space_needs" as FocusGroupStage,
        question: "q2",
        answers: [{ persona_id: "P001", text: "b", status: "answered" as const, error: null }],
      },
    ],
  };
  assert.equal(collectedAnswers(room).length, 2);
  assert.deepEqual(missingAnswers(room), [{ round: 0, persona_id: "P002" }]);
  assert.deepEqual(collectedAnswers(null), []);
});

test("the page shows the stage the student is in and lets them step back", () => {
  assert.match(
    pageSource,
    /FOCUS_GROUP_STAGES\.map\(\(entry, index\) => \([\s\S]*?onClick=\{\(\) => \{[\s\S]*?setStage\(entry\);[\s\S]*?disabled=\{readOnly \|\| busy \|\| !canAskStage\(room, entry\)\}/
  );
  assert.match(
    pageSource,
    /Stage \{FOCUS_GROUP_STAGES\.indexOf\(stage\) \+ 1\} of \{FOCUS_GROUP_STAGES\.length\}/
  );
  assert.match(pageSource, /every answer already collected\s*\n?\s*stays in the transcript/);
});

// --- cost after the fact, retries, memo, export -----------------------------

test("the page puts the actual spend next to the estimate it was approved against", () => {
  assert.match(
    pageSource,
    /Estimated \{formatFocusGroupCostEstimate\(Number\(room\.estimated_total_cost_usd \?\? room\.estimated_cost_usd\)\)\}[\s\S]*?actually[\s\S]*?room\.session_usage\.cost_usd/
  );
});

test("the page surfaces a budget stop and a missing-answer retry in plain words", () => {
  assert.match(
    pageSource,
    /room\.status === "budget_stopped" \|\| room\.status === "failed"[\s\S]*?\{room\.error\?\.message\}/
  );
  assert.match(
    pageSource,
    /onClick=\{\(\) => askRoom\(\{ retry: true \}\)\}[\s\S]*?Retry the \{missing\.length\} missing answer\(s\)/
  );
});

test("finished rooms can be re-opened, exported and deleted from the page", () => {
  assert.match(pageSource, /onClick=\{\(\) => openRoom\(entry\.room_id\)\}[\s\S]*?Re-open/);
  assert.match(pageSource, /onClick=\{\(\) => deleteRoom\(entry\.room_id\)\}[\s\S]*?Delete/);
  assert.match(pageSource, /onClick=\{\(\) => exportRoom\("markdown"\)\}[\s\S]*?Export transcript \+ memo/);
  assert.match(pageSource, /method: "DELETE"/);
});

test("the memo is only written after the student confirms its extra charge", () => {
  assert.match(
    pageSource,
    /authorize\s*&&\s*memo[\s\S]*?authorize_charge: true/
  );
  // Lin fix 5: the AI memo is optional feedback now; the confirm wording lives in aiMemoRetryLabel.
  assert.match(pageSource, /onClick=\{\(\) => loadMemo\(true\)\}[\s\S]*?\{aiMemoRetryLabel\(memo\)\}/);
  assert.match(pageSource, /onClick=\{\(\) => loadMemo\(\)\}[\s\S]*?AI draft memo/);
});

// --- classroom no-login -----------------------------------------------------

test("classroom no-login mode opens the focus-group page", () => {
  assert.equal(isClassroomFocusGroupPage("/focus-group"), true);
  assert.equal(isClassroomFocusGroupPage("/focus-group/"), true);
  assert.equal(isClassroomFocusGroupPage("/focus-groups"), false);
  assert.equal(isClassroomStudentPage("/focus-group"), true);
  assert.equal(isClassroomStudentPage("/interview"), true);
  assert.equal(isClassroomStudentPage("/focus-groups"), false);
  assert.equal(isClassroomStudentPage("/"), false);
  assert.match(middlewareSource, /isClassroomStudentPage\(pathname\)/);
});

test("classroom students can drive a room without hitting a login wall", () => {
  const allowed = [
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms"],
    ["GET", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms"],
    ["GET", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1"],
    ["GET", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/memo"],
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/ask"],
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/cancel"],
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/memo"],
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/export"],
    ["DELETE", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1"],
  ] as const;
  for (const [method, pathname] of allowed) {
    assert.equal(isClassroomInterviewApiRequest(pathname, method), true, `${method} ${pathname}`);
  }
  const refused = [
    ["DELETE", "/api/backend/api/v1/studies/std_1/interview/batches/batch_1"],
    ["POST", "/api/backend/api/v1/studies/std_1/interview/focus-group/rooms/fg_1/../../simulation-runs"],
    ["GET", "/api/backend/api/v1/studies/std_1/interview/insights"],
    [
      "POST",
      "/api/backend/api/v1/studies/..%2Fstd_victim%2Fsimulation-runs%3F/interview/focus-group/rooms",
    ],
  ] as const;
  for (const [method, pathname] of refused) {
    assert.equal(isClassroomInterviewApiRequest(pathname, method), false, `${method} ${pathname}`);
  }
});

test("a student can end their session so the next one on the device starts clean", () => {
  assert.match(endSessionSource, /cookies\.delete\(CLASSROOM_SESSION_COOKIE_NAME\)/);
  assert.match(middlewareSource, /pathname\.startsWith\("\/api\/classroom\/"\)/);
  // The control moved off the page and into the nav, where a sign-out would be. It is
  // reachable from both student pages, and only where there is no Clerk session to end.
  const userMenuSource = readFileSync(
    resolve(__dirname, "../../src/components/ui/user-menu-slot.tsx"),
    "utf8"
  );
  assert.match(userMenuSource, /isClassroomStudentPage\(pathname\)/);
  // Keyed on the classroom marker, not on which auth the deployment uses: classroom mode
  // runs with Clerk configured too, and there the student would otherwise have no way out.
  assert.match(userMenuSource, /CLASSROOM_MODE_COOKIE_NAME/);
  assert.doesNotMatch(
    userMenuSource,
    /isClerkConfigured[\s\S]{0,120}end-session/,
    "the end-session control must not be gated on Clerk being absent"
  );
  assert.match(middlewareSource, /CLASSROOM_MODE_COOKIE_NAME, "1"/);
  assert.match(endSessionSource, /cookies\.delete\(CLASSROOM_MODE_COOKIE_NAME\)/);
  assert.match(
    userMenuSource,
    /fetch\(\s*"\/api\/classroom\/end-session",[\s\S]*?window\.location\.reload\(\)/
  );
  // The rendered element, not the import line: deleting <WorkflowNav /> from the JSX takes
  // the only remaining end-session control off the page, and an import-only grep stays green.
  assert.match(pageSource, /<WorkflowNav\s*\/>/);
  // A failed clear must not look like a successful handoff.
  assert.match(userMenuSource, /if \(!response\?\.ok\)/);
});
