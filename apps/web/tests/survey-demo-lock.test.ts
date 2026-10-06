import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

import * as demoMode from "../src/lib/demo-mode";
import {
  ADDED_QUESTION_STATUS,
  DEMO_ADDED_QUESTIONS_NOTE,
  DEMO_AI_ACTION_NOTE,
  DEMO_RUN_LIVE_NOTE,
  SURVEY_AI_ACTIONS,
  addedQuestionStatus,
  aiReadOptions,
  applyDemoLockToRunControls,
  demoSwitchOn,
  isAiSummaryWithheld,
  isSurveyActionLocked,
  refuseIfDemoLocked,
} from "../src/lib/survey-demo-lock";
import { DEMO_INSIGHTS_HEADER, LLM_INSIGHTS_HEADER, NO_AI_SUMMARY_INSIGHTS_HEADER, insightsHeader } from "../src/lib/demo-run";
import { demoRunControl, liveRunControl, type BackendReadinessPayload } from "../src/lib/backend-readiness";
import { getInsights, getInterviewInsights } from "../src/lib/api";
// The section harness below loads these real helpers by their "@/lib/..." names, so they must be compiled too.
import "../src/lib/run-evidence";
import "../src/lib/run-counts";
import "../src/lib/utils";
import "../src/lib/setup-flow-utils";
import "../src/lib/product-reset";
import "../src/lib/answer-sourcing";
import "../src/lib/insights-chart-adapters";
import "../src/lib/interview-provenance";
import "../src/lib/interview-models";
import "../src/lib/survey-question-form";

const READY: BackendReadinessPayload = {
  ready: true, status: "ready", healthStatus: "ok", message: "Backend is ready.", providers: { jev: false, openrouter: true },
};
const TWO_MODELS = ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"];

/** Turn the app-wide switch on or off through its real store, the way the switch at the top of the page does. */
function switchSetTo(on: boolean) {
  const values = new Map<string, string>();
  const win = {
    localStorage: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) },
    dispatchEvent: () => true,
    addEventListener() {}, removeEventListener() {},
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    requestAnimationFrame: (callback: () => void) => { callback(); return 0; },
  };
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, value: win });
  demoMode.setDemoMode(on);
  assert.equal(demoMode.isDemoMode(), on);
  return {
    win,
    restore() {
      if (previous) Object.defineProperty(globalThis, "window", previous);
      else Reflect.deleteProperty(globalThis, "window");
    },
  };
}

async function withSwitch(on: boolean, body: (win: Record<string, unknown>) => Promise<void> | void) {
  const sw = switchSetTo(on);
  try { await body(sw.win); } finally { sw.restore(); }
}

/** A request the test holds open, so the switch can be turned on while a click waits on it. */
function held() {
  let release!: () => void;
  const promise = new Promise<void>((done) => { release = done; });
  return { promise, release };
}

// ---------------------------------------------------------------------------------------------------------------------
// Pure lock decisions
// ---------------------------------------------------------------------------------------------------------------------

test("survey demo lock: every AI action is locked only while the switch is on", () => {
  for (const action of SURVEY_AI_ACTIONS) {
    assert.equal(isSurveyActionLocked(action, false, "general"), false, action);
    assert.equal(refuseIfDemoLocked(action, false, "general"), null, action);
    assert.equal(isSurveyActionLocked(action, true, "general"), true, action);
  }
  assert.equal(refuseIfDemoLocked("run_live", true), DEMO_RUN_LIVE_NOTE);
  for (const action of SURVEY_AI_ACTIONS.filter((name) => name !== "run_live")) {
    assert.equal(refuseIfDemoLocked(action, true, "general"), DEMO_AI_ACTION_NOTE, action);
  }
  assert.equal(DEMO_RUN_LIVE_NOTE, "Demo (no AI): read-only. Turn Demo off at the top of the page to run live.");
  assert.ok(DEMO_AI_ACTION_NOTE.startsWith(demoMode.DEMO_READ_ONLY));
});

test("survey demo lock: a Neo study's interview run loads seeded transcripts with no model, so it stays open", () => {
  assert.equal(isSurveyActionLocked("interview_run", true, "neo_smart"), false);
  assert.equal(isSurveyActionLocked("interview_run", true, "general"), true);
  assert.equal(isSurveyActionLocked("interview_run", true, null), true);   // an unknown study mode fails closed
  // The follow-up chat always calls a model, Neo or not.
  assert.equal(isSurveyActionLocked("interview_chat", true, "neo_smart"), true);
});

test("switch on: Run live is disabled and the preloaded demo stays the one enabled action", async () => {
  await withSwitch(true, () => {
    // A click or effect reads the stored switch even if the render has not caught up with it yet.
    assert.equal(demoSwitchOn(false), true);
    const controls = applyDemoLockToRunControls(demoSwitchOn(false), liveRunControl(TWO_MODELS, READY), demoRunControl(READY));
    assert.equal(controls.live.enabled, false);
    assert.equal(controls.live.label, "Run live");
    assert.equal(controls.live.hint, null);   // the lock note is shown on its own; no "no key" hint for a locked button
    assert.equal(controls.demo.enabled, true);
  });
});

test("switch on with the server unknown keeps the hint that also explains why the demo is off", () => {
  const live = liveRunControl(TWO_MODELS, null);
  const controls = applyDemoLockToRunControls(true, live, demoRunControl(null));
  assert.equal(controls.live.enabled, false);
  assert.equal(controls.demo.enabled, false);
  assert.equal(controls.live.hint, live.hint);
  assert.match(controls.live.hint ?? "", /preloaded demo are unavailable/);
});

test("switch off: the run controls come back untouched", async () => {
  await withSwitch(false, () => {
    assert.equal(demoSwitchOn(false), false);
    const live = liveRunControl(TWO_MODELS, READY);
    const demo = demoRunControl(READY);
    const controls = applyDemoLockToRunControls(demoSwitchOn(false), live, demo);
    assert.equal(controls.live, live);
    assert.equal(controls.demo, demo);
    assert.equal(controls.live.enabled, true);
  });
});

test("insight reads ask the server for no AI only while the switch is on", () => {
  assert.deepEqual(aiReadOptions(true), { ai: false });
  assert.deepEqual(aiReadOptions(false), { ai: true });
});

test("the insights requests add ai=false only when asked; otherwise the request is unchanged", async () => {
  const previous = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = (async (url: string) => {
    urls.push(String(url));
    return new Response(JSON.stringify({ data: { insights: { available: false }, interview_insights: { available: false } } }), { status: 200 });
  }) as typeof fetch;
  try {
    await getInsights("std_1");
    await getInsights("std_1", { ai: true });
    await getInsights("std_1", { ai: false });
    await getInterviewInsights("std_1");
    await getInterviewInsights("std_1", { ai: true });
    await getInterviewInsights("std_1", { ai: false });
  } finally {
    globalThis.fetch = previous;
  }
  const base = "/api/backend/api/v1/studies/std_1";
  assert.deepEqual(urls, [
    `${base}/insights`, `${base}/insights`, `${base}/insights?ai=false`,
    `${base}/interview/insights`, `${base}/interview/insights`, `${base}/interview/insights?ai=false`,
  ]);
});

// ---------------------------------------------------------------------------------------------------------------------
// The real sections, rendered with deterministic hooks: buttons, notes, and handlers called directly
// ---------------------------------------------------------------------------------------------------------------------

type Element = { type: unknown; props: Record<string, any> };

const COMPONENT_STUBS = new Proxy({}, { get: (_target, key) => (typeof key === "string" ? key : undefined) });
const FRAMER = { motion: { div: "div" }, AnimatePresence: "presence" };
/** The switch as the sections read it: the hook's value comes from the same store the switch writes. */
const SWITCH_MODULE = { ...demoMode, useDemoMode: () => [demoMode.isDemoMode(), demoMode.setDemoMode] as const };

function mountSection(
  file: string,
  exportName: string,
  mocks: Record<string, unknown>,
  options: { props?: Record<string, unknown>; fetch?: (url: string) => Promise<unknown> } = {}
) {
  const slots: any[] = [];
  let cursor = 0;
  let pending: (() => unknown)[] = [];
  const react = {
    useState(initial: unknown) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = typeof initial === "function" ? (initial as () => unknown)() : initial;
      return [slots[i], (value: unknown) => {
        slots[i] = typeof value === "function" ? (value as (current: unknown) => unknown)(slots[i]) : value;
      }];
    },
    useRef(initial: unknown) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { current: initial };
      return slots[i];
    },
    useMemo(factory: () => unknown) { cursor++; return factory(); },
    useCallback(callback: unknown) { cursor++; return callback; },
    useEffect(effect: () => unknown, deps?: unknown[]) {
      const i = cursor++;
      const previous = slots[i] as unknown[] | undefined;
      if (!(i in slots) || !deps || !previous || deps.some((dep, k) => !Object.is(dep, previous[k]))) pending.push(effect);
      slots[i] = deps;
    },
  };
  const load = (name: string) => {
    if (name === "react") return react;
    if (name in mocks) return mocks[name];
    if (name === "framer-motion") return FRAMER;
    if (name.startsWith("@/components/")) return COMPONENT_STUBS;
    if (name.startsWith("@/lib/")) return require(resolve(__dirname, "../src/lib", name.slice("@/lib/".length)));
    return require(name);
  };
  const source = readFileSync(resolve(__dirname, "../../src/components/sections", file), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exported: Record<string, any> = {};
  const fetchMock = options.fetch ?? (async (url: string) => { throw new Error(`unexpected fetch ${url}`); });
  new Function("require", "exports", "window", "fetch", compiled)(load, exported, (globalThis as any).window, fetchMock);
  const component = exported[exportName];
  assert.equal(typeof component, "function", `${file} does not export ${exportName}`);
  let tree: unknown;
  function render() {
    cursor = 0;
    tree = component(options.props ?? {});
    const effects = pending;
    pending = [];
    effects.forEach((effect) => effect());
    return tree;
  }
  function flatten(node: any): Element[] {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(flatten);
    return [node, ...flatten(node.props?.children)];
  }
  function text(node: any): string {
    if (node == null || typeof node === "boolean") return "";
    if (Array.isArray(node)) return node.map(text).join("");
    if (typeof node === "object") return text(node.props?.children);
    return String(node);
  }
  render();
  return {
    render,
    async settle() {
      for (let round = 0; round < 3; round++) {
        await new Promise((done) => setImmediate(done));
        render();
      }
    },
    text: () => text(tree),
    nodes: () => flatten(tree),
    button(label: string) {
      const match = flatten(tree).find((node) => (node.type === "Button" || node.type === "button") && text(node).includes(label));
      assert.ok(match, `Missing button ${label}`);
      return match;
    },
    find(predicate: (node: Element) => boolean, what: string) {
      const match = flatten(tree).find(predicate);
      assert.ok(match, `Missing ${what}`);
      return match;
    },
  };
}

function studyContext(study: Record<string, unknown>, overrides: { createOrLoadStudy?: () => Promise<string> } = {}) {
  return {
    "@/providers/study-provider": {
      useStudy: () => ({
        studyId: "std_1",
        study,
        createOrLoadStudy: overrides.createOrLoadStudy ?? (async () => "std_1"),
        isCreatingStudy: false,
        isHydratingStudy: false,
        refreshStudy: async () => undefined,
      }),
    },
    "@/providers/section-registry-provider": {
      useSectionRegistry: () => ({ scrollToSection() {}, setNavigationLocked() {} }),
    },
    "@/lib/demo-mode": SWITCH_MODULE,
  };
}

const READY_STUDY = {
  updated_at: "2026-10-06T00:00:00Z",
  study_mode: { status: "saved", value: "general" },
  audience: { status: "saved" },
  survey: { status: "saved" },
  experiment: { status: "saved", value: { selected_models: TWO_MODELS } },
};

function mountRunStep() {
  const runs: string[] = [];
  const fetches: string[] = [];
  // Set one of these to hold the next readiness check or study save open.
  const holds: { readiness: Promise<void> | null; study: Promise<void> | null } = { readiness: null, study: null };
  const studySaves: string[] = [];
  const ui = mountSection("run-simulation-section.tsx", "RunSimulationSection", {
    ...studyContext(READY_STUDY, {
      createOrLoadStudy: async () => {
        studySaves.push("std_1");
        if (holds.study) await holds.study;
        return "std_1";
      },
    }),
    "@/lib/api": {
      clearLatestSimulationRun: async () => ({}),
      getLatestSimulationRun: async () => null,
      getLatestStabilityCheck: async () => null,
      startSimulationRun: async (_studyId: string, source: string) => {
        runs.push(source);
        return { simulationRun: null };
      },
    },
  }, {
    fetch: async (url: string) => {
      fetches.push(url);
      if (holds.readiness) await holds.readiness;
      return { json: async () => READY };
    },
  });
  return { ui, runs, fetches, holds, studySaves };
}

test("switch on: the Run step shows Run live disabled with its note, the demo enabled, and runs nothing by itself", async () => {
  await withSwitch(true, async () => {
    const { ui, runs, fetches } = mountRunStep();
    await ui.settle();
    assert.equal(ui.button("Run live").props.disabled, true);
    assert.equal(ui.button("Show preloaded demo (no AI)").props.disabled, false);
    assert.ok(ui.text().includes(DEMO_RUN_LIVE_NOTE));
    assert.doesNotMatch(ui.text(), /No AI key on this server/);
    assert.deepEqual(runs, []);   // the demo is never loaded by itself: the last live run stays until a click

    // The handler refuses a live run even when called directly: no readiness check, no request.
    const fetchesBefore = fetches.length;
    await ui.button("Run live").props.onClick();
    await ui.settle();
    assert.deepEqual(runs, []);
    assert.equal(fetches.length, fetchesBefore);
    assert.ok(ui.nodes().some((node) => node.props?.message === DEMO_RUN_LIVE_NOTE));

    // The preloaded demo still runs, on its click.
    await ui.button("Show preloaded demo (no AI)").props.onClick();
    await ui.settle();
    assert.deepEqual(runs, ["demo"]);
  });
});

test("switch off: the Run step is exactly as before (Run live and the demo enabled, no note)", async () => {
  await withSwitch(false, async () => {
    const { ui, runs } = mountRunStep();
    await ui.settle();
    assert.equal(ui.button("Run live").props.disabled, false);
    assert.equal(ui.button("Show preloaded demo (no AI)").props.disabled, false);
    assert.ok(!ui.text().includes(DEMO_RUN_LIVE_NOTE));
    await ui.button("Run live").props.onClick();
    await ui.settle();
    assert.deepEqual(runs, ["live"]);
  });
});

test("switch on: the stability check is locked and its handler refuses a direct call", async () => {
  await withSwitch(true, async () => {
    let started = 0;
    const ui = mountSection("stability-check-panel.tsx", "StabilityCheckPanel", {
      "@/lib/demo-mode": SWITCH_MODULE,
      "@/lib/api": { getLatestStabilityCheck: async () => null, startStabilityCheck: async () => { started++; return null; } },
    }, { props: { studyId: "std_1" } });
    await ui.settle();
    assert.equal(ui.button("Run Stability Check").props.disabled, true);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
    await ui.button("Run Stability Check").props.onClick();
    await ui.settle();
    assert.equal(started, 0);
    assert.ok(ui.nodes().some((node) => node.props?.message === DEMO_AI_ACTION_NOTE));
  });
});

test("switch on: product URL autofill and image analysis are locked and refused when called directly; non-AI controls stay open", async () => {
  await withSwitch(true, async () => {
    const calls: string[] = [];
    const study = {
      ...READY_STUDY,
      product: { status: "not_started" },
      product_enrichments: {
        latest_url_autofill: null,
        latest_image_analysis: { analysis: { labels: ["Studio"] }, proposed_product_patch: {}, completed_at: "2026-10-06T00:00:00Z" },
      },
    };
    const ui = mountSection("product-section.tsx", "ProductSection", {
      ...studyContext(study),
      "@/lib/api": {
        runProductUrlAutofill: async () => { calls.push("url"); return {}; },
        runProductImageAnalysis: async () => { calls.push("image"); return {}; },
        saveProduct: async () => ({}),
      },
    });
    await ui.settle();

    ui.find((node) => node.type === "TextInput" && node.props.placeholder === "https://example.com/product", "URL input")
      .props.onChange("https://example.com/tahoe-mini");
    const upload = ui.find((node) => node.type === "input" && node.props.type === "file", "image upload input");
    upload.props.onChange({ target: { files: [new File(["png"], "studio.png", { type: "image/png" })] } });
    await ui.settle();

    assert.equal(ui.button("Autofill from URL").props.disabled, true);
    assert.equal(ui.button("Analyze Image").props.disabled, true);
    assert.equal(ui.button("Reset Product Details").props.disabled, undefined);   // not an AI action

    await ui.button("Autofill from URL").props.onClick();
    await ui.button("Analyze Image").props.onClick();
    await ui.settle();
    assert.deepEqual(calls, []);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
  });
});

test("switch on: survey generation is locked and refused when called directly", async () => {
  await withSwitch(true, async () => {
    let generated = 0;
    const ui = mountSection("survey-generator-panel.tsx", "SurveyGeneratorPanel", {
      "@/lib/demo-mode": SWITCH_MODULE,
      "@/lib/api": { generateSurvey: async () => { generated++; return {}; }, acceptGeneratedSurvey: async () => ({}) },
    }, { props: { studyId: "std_1", onAccepted() {}, onEnsureStudy: async () => "std_1" } });
    ui.button("Open Generator").props.onClick();
    ui.render();
    assert.equal(ui.button("Generate Survey").props.disabled, true);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
    await ui.button("Generate Survey").props.onClick();
    await ui.settle();
    assert.equal(generated, 0);
  });
});

function mountInterviewRun(
  studyMode: string,
  options: { savedQuestions?: { id: string; text: string }[]; saveHold?: Promise<void> } = {}
) {
  const runs: unknown[] = [];
  const saves: unknown[] = [];
  const ui = mountSection("interview-synthesis-section.tsx", "InterviewSynthesisSection", {
    ...studyContext({ ...READY_STUDY, study_mode: { status: "saved", value: studyMode } }),
    "@/lib/api": {
      getInterviewSynthesis: async () => ({
        latest_run: null,
        value: options.savedQuestions ? { questions: options.savedQuestions } : null,
      }),
      getLatestInterviewRun: async () => null,
      saveInterviewSynthesisConfig: async (_studyId: string, payload: unknown) => {
        saves.push(payload);
        if (options.saveHold) await options.saveHold;
        return {};
      },
      startInterviewRun: async (_studyId: string, payload: unknown) => { runs.push(payload); return { status: "completed" }; },
    },
  });
  return { ui, runs, saves };
}

test("switch on: a custom study's interview run is locked and refused when called directly", async () => {
  await withSwitch(true, async () => {
    const { ui, runs } = mountInterviewRun("general");
    await ui.settle();
    assert.equal(ui.button("Run Interviews").props.disabled, true);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
    await ui.button("Run Interviews").props.onClick();
    await ui.settle();
    assert.deepEqual(runs, []);
  });
});

test("switch on: a Neo study's interview run (seeded, no model) stays available", async () => {
  await withSwitch(true, async () => {
    const { ui, runs } = mountInterviewRun("neo_smart");
    await ui.settle();
    assert.equal(ui.button("Run Interviews").props.disabled, false);
    assert.ok(!ui.text().includes(DEMO_AI_ACTION_NOTE));
    await ui.button("Run Interviews").props.onClick();
    await ui.settle();
    assert.equal(runs.length, 1);
  });
});

test("switch on: interview insights are read with ai=false and the follow-up chat is locked and refused", async () => {
  await withSwitch(true, async () => {
    const reads: unknown[] = [];
    const sent: unknown[] = [];
    const run = {
      status: "completed",
      persona_count: 1,
      pairs: [{
        persona_id: "neo-001",
        persona: { fit_tier: "strong", segment_label: "Backyard office" },
        model_a: { model: "openai/gpt-4o-mini", answers: { IQ1: "A home office." } },
        model_b: { model: "google/gemini-2.0-flash-001", answers: { IQ1: "An office." } },
      }],
    };
    const ui = mountSection("interview-insights-section.tsx", "InterviewInsightsSection", {
      ...studyContext(READY_STUDY),
      "@/lib/api": {
        getInterviewInsights: async (_studyId: string, options: unknown) => { reads.push(options); return { available: false, message: "none" }; },
        getLatestInterviewRun: async () => run,
        sendInterviewChatMessage: async (_studyId: string, payload: unknown) => { sent.push(payload); return {}; },
        InterviewChatApiError: class extends Error {},
      },
    });
    await ui.settle();
    assert.deepEqual(reads, [{ ai: false }]);

    ui.find((node) => node.type === "textarea" && String(node.props.placeholder).startsWith("Ask this persona"), "chat box")
      .props.onChange({ target: { value: "What would make you trust the install?" } });
    ui.render();
    assert.equal(ui.button("Send follow-up").props.disabled, true);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
    await ui.find((node) => node.type === "form", "chat form").props.onSubmit({ preventDefault() {} });
    await ui.settle();
    assert.deepEqual(sent, []);
  });
});

test("the survey insights are read with ai=false while the switch is on, and as before while it is off", async () => {
  for (const on of [true, false]) {
    await withSwitch(on, async () => {
      const reads: unknown[] = [];
      const ui = mountSection("insights-section.tsx", "InsightsSection", {
        ...studyContext(READY_STUDY),
        "@/lib/api": { getInsights: async (_studyId: string, options: unknown) => { reads.push(options); return { available: false }; } },
      });
      await ui.settle();
      assert.deepEqual(reads, [{ ai: !on }]);
    });
  }
});

test("switch on: the add-question card keeps adding questions and says they need a live run", async () => {
  for (const on of [true, false]) {
    await withSwitch(on, () => {
      const ui = mountSection("add-question-card.tsx", "AddQuestionCard", {
        "@/lib/demo-mode": SWITCH_MODULE,
        "@/lib/api": { addSurveyQuestion: async () => ({}), removeSurveyQuestion: async () => ({}) },
      }, { props: { studyId: "std_1", questions: [], onChanged() {} } });
      assert.equal(ui.button("Add question").props.disabled, false);
      assert.equal(ui.text().includes(DEMO_ADDED_QUESTIONS_NOTE), on);
    });
  }
  assert.equal(DEMO_ADDED_QUESTIONS_NOTE, "Added questions need a live run — turn Demo off at the top of the page to answer them.");
});

// ---------------------------------------------------------------------------------------------------------------------
// The switch turned on while a click is already waiting on the server: nothing reaches a provider after that
// ---------------------------------------------------------------------------------------------------------------------

test("switch turned on while Run live waits on its readiness check: no live run is posted", async () => {
  await withSwitch(false, async () => {
    const { ui, runs, holds, studySaves } = mountRunStep();
    await ui.settle();
    const readiness = held();
    holds.readiness = readiness.promise;

    const click = ui.button("Run live").props.onClick();
    ui.render();
    assert.ok(ui.text().includes("Running live..."));
    demoMode.setDemoMode(true);   // the student turns Demo on at the top of the page while the click waits
    readiness.release();
    await click;
    await ui.settle();

    assert.deepEqual(runs, []);
    assert.deepEqual(studySaves, []);   // refused right after the readiness check, before anything else is sent
    assert.ok(ui.nodes().some((node) => node.props?.message === DEMO_RUN_LIVE_NOTE));
    assert.ok(!ui.text().includes("Running live..."));
    assert.equal(ui.button("Run live").props.disabled, true);
    assert.equal(ui.button("Show preloaded demo (no AI)").props.disabled, false);
  });
});

test("switch turned on while Run live waits on the study save: no live run is posted", async () => {
  await withSwitch(false, async () => {
    const { ui, runs, holds } = mountRunStep();
    await ui.settle();
    const save = held();
    holds.study = save.promise;

    const click = ui.button("Run live").props.onClick();
    await new Promise((done) => setImmediate(done));   // past the readiness check, now waiting on the study save
    ui.render();
    assert.ok(ui.text().includes("Running live..."));
    demoMode.setDemoMode(true);
    save.release();
    await click;
    await ui.settle();

    assert.deepEqual(runs, []);
    assert.ok(ui.nodes().some((node) => node.props?.message === DEMO_RUN_LIVE_NOTE));
    assert.ok(!ui.text().includes("Running live..."));
    assert.ok(!ui.text().includes("Execution progress"));

    // The demo still runs on its click afterwards.
    holds.study = null;
    await ui.button("Show preloaded demo (no AI)").props.onClick();
    await ui.settle();
    assert.deepEqual(runs, ["demo"]);
  });
});

test("switch left off while Run live waits: the live run goes ahead as before", async () => {
  await withSwitch(false, async () => {
    const { ui, runs, holds } = mountRunStep();
    await ui.settle();
    const readiness = held();
    holds.readiness = readiness.promise;
    const click = ui.button("Run live").props.onClick();
    readiness.release();
    await click;
    await ui.settle();
    assert.deepEqual(runs, ["live"]);
  });
});

test("switch turned on while a custom study's interview questions are saving: the interview models are not called", async () => {
  await withSwitch(false, async () => {
    const save = held();
    const { ui, runs, saves } = mountInterviewRun("general", {
      savedQuestions: [{ id: "IQ1", text: "How would you use a backyard studio?" }],
      saveHold: save.promise,
    });
    await ui.settle();
    ui.button("Custom questions").props.onClick();   // open the config panel, so the run saves the questions first
    ui.render();

    const click = ui.button("Run Interviews").props.onClick();
    assert.equal(saves.length, 1);
    demoMode.setDemoMode(true);
    save.release();
    await click;
    await ui.settle();

    assert.deepEqual(runs, []);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
    assert.equal(ui.button("Run Interviews").props.disabled, true);
  });
});

test("switch turned on while product autofill or image analysis waits on the study save: neither provider is called", async () => {
  await withSwitch(false, async () => {
    const calls: string[] = [];
    let hold: Promise<void> | null = null;
    const study = { ...READY_STUDY, product: { status: "not_started" }, product_enrichments: {} };
    const ui = mountSection("product-section.tsx", "ProductSection", {
      ...studyContext(study, {
        createOrLoadStudy: async () => {
          if (hold) await hold;
          return "std_1";
        },
      }),
      "@/lib/api": {
        runProductUrlAutofill: async () => { calls.push("url"); return {}; },
        runProductImageAnalysis: async () => { calls.push("image"); return {}; },
        saveProduct: async () => ({}),
      },
    });
    await ui.settle();
    ui.find((node) => node.type === "TextInput" && node.props.placeholder === "https://example.com/product", "URL input")
      .props.onChange("https://example.com/tahoe-mini");
    ui.find((node) => node.type === "input" && node.props.type === "file", "image upload input")
      .props.onChange({ target: { files: [new File(["png"], "studio.png", { type: "image/png" })] } });
    await ui.settle();

    const urlSave = held();
    hold = urlSave.promise;
    const autofill = ui.button("Autofill from URL").props.onClick();
    demoMode.setDemoMode(true);
    urlSave.release();
    await autofill;
    await ui.settle();
    assert.deepEqual(calls, []);
    // The status line (a plain div here) now carries the lock note instead of "Generating draft details from URL...".
    assert.ok(ui.nodes().some((node) => node.type === "div" && node.props.children === DEMO_AI_ACTION_NOTE));
    assert.ok(!ui.text().includes("Generating draft details from URL"));

    demoMode.setDemoMode(false);
    await ui.settle();
    const imageSave = held();
    hold = imageSave.promise;
    const analyze = ui.button("Analyze Image").props.onClick();
    demoMode.setDemoMode(true);
    imageSave.release();
    await analyze;
    await ui.settle();
    assert.deepEqual(calls, []);
    assert.ok(!ui.text().includes("Analyzing product image"));
  });
});

test("switch turned on while survey generation waits on the new study: the generator is not called", async () => {
  await withSwitch(false, async () => {
    let generated = 0;
    const ensure = held();
    const ui = mountSection("survey-generator-panel.tsx", "SurveyGeneratorPanel", {
      "@/lib/demo-mode": SWITCH_MODULE,
      "@/lib/api": { generateSurvey: async () => { generated++; return {}; }, acceptGeneratedSurvey: async () => ({}) },
    }, {
      props: {
        studyId: null,
        onAccepted() {},
        onEnsureStudy: async () => { await ensure.promise; return "std_1"; },
      },
    });
    ui.button("Open Generator").props.onClick();
    ui.render();
    const click = ui.button("Generate Survey").props.onClick();
    demoMode.setDemoMode(true);
    ensure.release();
    await click;
    await ui.settle();
    assert.equal(generated, 0);
    assert.ok(ui.text().includes(DEMO_AI_ACTION_NOTE));
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Wording under the switch: the Insights header and the add-question card
// ---------------------------------------------------------------------------------------------------------------------

test("insights header: with the switch on and no AI summary, it does not say the LLM summarized the insights", () => {
  assert.equal(isAiSummaryWithheld(true, false), true);
  assert.equal(isAiSummaryWithheld(true, undefined), true);
  assert.equal(isAiSummaryWithheld(true, true), false);    // a cached summary is still served and is still the LLM's
  assert.equal(isAiSummaryWithheld(false, false), false);  // switch off: unchanged

  const withheld = insightsHeader("jev_live", { aiSummaryWithheld: true });
  assert.equal(withheld, NO_AI_SUMMARY_INSIGHTS_HEADER);
  assert.doesNotMatch(`${withheld.title} ${withheld.description}`, /LLM/);
  // The gold box under it already says no AI summary was generated; the header does not say it again.
  assert.doesNotMatch(withheld.description, /no AI summary was generated/);
  assert.equal(insightsHeader("jev_live", { aiSummaryWithheld: false }), LLM_INSIGHTS_HEADER);
  assert.equal(insightsHeader("jev_live"), LLM_INSIGHTS_HEADER);
  assert.equal(insightsHeader("demo_preloaded", { aiSummaryWithheld: true }), DEMO_INSIGHTS_HEADER);
});

test("insights section: the header follows the switch and the summary the server returned", async () => {
  const noSummary = { available: false, message: "Demo (no AI) is on: no AI summary was generated. Turn Demo off to get one." };
  const cases = [
    { on: true, llm: noSummary, title: NO_AI_SUMMARY_INSIGHTS_HEADER.title },
    { on: true, llm: { available: true, cached: true, overview: "Cached." }, title: LLM_INSIGHTS_HEADER.title },
    { on: false, llm: { available: false, message: "No key." }, title: LLM_INSIGHTS_HEADER.title },
  ];
  for (const { on, llm, title } of cases) {
    await withSwitch(on, async () => {
      const ui = mountSection("insights-section.tsx", "InsightsSection", {
        ...studyContext(READY_STUDY),
        "@/lib/api": {
          getInsights: async () => ({ available: false, run: { generation_mode: "jev_live" }, llm_summary: llm }),
        },
      });
      await ui.settle();
      const header = ui.find((node) => node.type === "SectionHeader", "section header");
      assert.equal(header.props.title, title, `switch ${on ? "on" : "off"}, summary ${llm.available}`);
    });
  }
});

test("add-question card: with the switch on the success line is just 'Added.'; off it is unchanged", async () => {
  assert.equal(addedQuestionStatus(ADDED_QUESTION_STATUS, true), "Added.");
  assert.equal(addedQuestionStatus(ADDED_QUESTION_STATUS, false), "Added. Run live to get answers to it.");
  assert.equal(addedQuestionStatus("Could not add the question.", true), "Could not add the question.");
  assert.equal(addedQuestionStatus(null, true), null);

  for (const on of [true, false]) {
    await withSwitch(on, async () => {
      const ui = mountSection("add-question-card.tsx", "AddQuestionCard", {
        "@/lib/demo-mode": SWITCH_MODULE,
        "@/lib/api": { addSurveyQuestion: async () => ({}), removeSurveyQuestion: async () => ({}) },
      }, { props: { studyId: "std_1", questions: [], onChanged() {} } });
      ui.find((node) => node.type === "textarea", "question text").props.onChange({ target: { value: "How likely are you to buy it?" } });
      ui.render();
      await ui.button("Add question").props.onClick();
      await ui.settle();
      const status = ui.find((node) => node.props?.role === "status", "status line");
      const shown = String(status.props.children);
      assert.equal(shown, on ? "Added." : ADDED_QUESTION_STATUS);
      // The live-run point is made once on the card, by the note, while the switch is on.
      assert.equal(ui.text().split("live run").length - 1, on ? 1 : 0);

      // Flipping the switch after the add updates the line with it.
      demoMode.setDemoMode(!on);
      ui.render();
      assert.equal(String(ui.find((node) => node.props?.role === "status", "status line").props.children), on ? ADDED_QUESTION_STATUS : "Added.");
    });
  }
});
