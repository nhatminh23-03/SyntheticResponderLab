import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { batchExport, REFLECTION_PROMPTS } from "../src/lib/interview-batch-export";
import { InterviewChatApiError, sendInterviewChatMessage } from "../src/lib/api";
import { InterviewOperationError } from "../src/lib/standalone-interview";
import * as modelHelpers from "../src/lib/interview-models";
import * as comparisonHelpers from "../src/lib/interview-comparison";
import { isClassroomInterviewApiRequest } from "../src/lib/classroom-access";

// Render the actual page with deterministic hooks and transport. This exercises its
// event handlers and rendered controls without a browser or a paid provider.
type Element = { type: unknown; props: Record<string, any> };
function harness(savedBatches: any[] = [], comparisonFetcher?: Parameters<typeof comparisonHelpers.runInterviewComparison>[1], carried?: Map<string, string>, demoPlayback = false) {
  let demoEnabled = demoPlayback;
  let confirmResult = true;
  const confirmations: string[] = [];
  const states: any[] = [];
  let cursor = 0;
  const effects: (() => void)[] = [];
  let first = true;
  const calls: { path: string; payload: any }[] = [];
  const chatCalls: any[] = [];
  const models = [
    { id: "cheap-a", name: "A", tier: "cheap", prompt_price_per_million: 0.1, completion_price_per_million: 0.2, estimated_cost_per_persona_usd: .001 },
    { id: "cheap-b", name: "B", tier: "cheap", prompt_price_per_million: 0.2, completion_price_per_million: 0.3, estimated_cost_per_persona_usd: .002 },
    { id: "expensive-a", name: "Expensive A", tier: "expensive", prompt_price_per_million: 3, completion_price_per_million: 15, estimated_cost_per_persona_usd: .05 },
  ];
  const personas = ["neo-001", "neo-002", "neo-003"].map(persona_id => ({ persona_id, lifestyle_tags: [], census_profile: "Household" }));
  const memory = carried ?? new Map<string, string>();
  let transport: (path: string, payload: any) => Promise<any> = async (path) => {
    if (path === "demo/batch") {
      const fixture = JSON.parse(readFileSync(resolve(__dirname, "../../../api/seed_data/demo/batch.json"), "utf8"));
      return { batch: { ...fixture.config, ...fixture.state, demo: true, provisional: true, job_id: "demo_batch",
        status: "completed", session_usage: { cost_usd: "0" }, error: null } };
    }
    throw new Error("unexpected request");
  };
  let exportsPayload: any;
  const exportedMemos: any[] = [];
  const exportedStudentMemos: any[] = [];
  const api = {
    getInterviewPersonas: async () => ({ personas, source: "database" }),
    getInterviewModelCatalog: async () => ({ models, defaultModelId: "cheap-a", pricingAsOf: "test", personaCount: { minimum: 3, maximum: 30, default: 3 }, costEstimate: null }),
    sendInterviewChatMessage: async (_id: string, payload: any) => {
      chatCalls.push(payload);
      return { session_id: "ses_1", reply: `Original ${chatCalls.length}`, answer_id: `ans_${chatCalls.length}`, version: 0 };
    },
    getInterviewTranscriptExport: async (_id: string, payload: any) => {
      exportsPayload = payload;
      return { blob: new Blob(["transcript"]), filename: "test.md" };
    },
    InterviewChatApiError,
  };
  const react = {
    useState(initial: any) {
      const i = cursor++;
      if (!(i in states)) states[i] = typeof initial === "function" ? initial() : initial;
      return [states[i], (value: any) => { states[i] = typeof value === "function" ? value(states[i]) : value; }];
    },
    useRef(initial: any) {
      const i = cursor++;
      if (!(i in states)) states[i] = { current: initial };
      return states[i];
    },
    useEffect(effect: () => void) { if (first) effects.push(effect); },
  };
  const mocks: Record<string, any> = {
    react,
    "@/components/demo/demo-mode": { DemoScreens: "demo-screens", DemoNotice: "demo-notice", useDemoActivity() {} },
    "@/lib/demo-mode": { useDemoMode: () => [demoEnabled, () => {}], isDemoMode: () => demoEnabled },
    "framer-motion": { AnimatePresence: "presence", motion: { div: "div" } },
    "@/lib/api": api,
    "@/lib/interview-batch-export": { REFLECTION_PROMPTS, batchExport: (...args: Parameters<typeof batchExport>) => {
      exportedMemos.push(args[2]); exportedStudentMemos.push(args[3]); return batchExport(...args);
    } },
    "@/lib/interview-models": modelHelpers,
    "@/lib/interview-comparison": { ...comparisonHelpers, runInterviewComparison: comparisonFetcher
      ? (input: Parameters<typeof comparisonHelpers.runInterviewComparison>[0]) => comparisonHelpers.runInterviewComparison(input, comparisonFetcher)
      : async () => [
      { modelId: "cheap-a", answer: "Card A", answerId: "card_a", version: 0 },
      { modelId: "cheap-b", answer: "Card B", answerId: "card_b", version: 0 },
    ] },
    "@/lib/standalone-interview": { InterviewOperationError, interviewOperation: async (_id: string, path: string, payload: any) => {
      if (path === "batches" && !payload) return { batches: savedBatches };
      calls.push({ path, payload }); return transport(path, payload);
    } },
    "@/lib/utils": { cn: (...args: unknown[]) => args.filter(Boolean).join(" ") },
    "@/providers/study-provider": { StudyProvider: "provider", useStudy: () => ({ studyId: "std_1" }) },
  };
  mocks["@/providers/theme-provider"] = { ThemeProvider: "theme-provider", useTheme: () => ({ theme: "dark", toggle() {} }) };
  for (const [file, component] of [["badge-chip", "BadgeChip"], ["button", "Button"], ["glass-panel", "GlassPanel"], ["workflow-nav", "WorkflowNav"]]) {
    mocks[`@/components/ui/${file}`] = { [component]: component };
  }
  const source = readFileSync(resolve(__dirname, "../../src/app/interview/page.tsx"), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exported: any = {};
  const storage = { getItem: (key: string) => memory.get(key) ?? null, setItem: (key: string, value: string) => memory.set(key, value), removeItem: (key: string) => memory.delete(key) };
  const dom = { createElement: () => ({ click() {}, remove() {} }), body: { appendChild() {} } };
  new Function("require", "exports", "localStorage", "document", "window", compiled)((name: string) => mocks[name] ?? require(name), exported, storage, dom, { confirm: (message: string) => { confirmations.push(message); return confirmResult; } });
  // ponytail: the page's default export is just provider wrappers; find the one real component inside.
  const findComponent = (node: any): any => typeof node === "function"
    ? findComponent(node(demoPlayback))
    : Array.isArray(node)
    ? node.map(findComponent).find(Boolean)
    : node && typeof node === "object"
      ? (typeof node.type === "function" ? node.type : findComponent(node.props?.children))
      : null;
  const component = findComponent(exported.default());
  assert.ok(component, "interview page renders no component inside its providers");
  let tree: Element;
  function render() { cursor = 0; tree = component({ demoPlayback }); first = false; return tree; }
  render();
  effects.forEach(effect => effect());
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
  return {
    calls, chatCalls, memory, api, confirmations, exportedMemos, exportedStudentMemos,
    setDemo(enabled: boolean) { demoEnabled = enabled; },
    dismissConfirmation() { confirmResult = false; },
    get exportedTranscript() { return exportsPayload; },
    setTransport(fn: typeof transport) { transport = fn; },
    async settle() { await new Promise(resolve => setImmediate(resolve)); render(); },
    render,
    text() { return text(tree); },
    nodes() { return flatten(tree); },
    button(label: string) {
      const match = flatten(tree).find(node => (node.type === "Button" || node.type === "button") && text(node).includes(label));
      assert.ok(match, `Missing button ${label}`); return match;
    },
  };
}

const batch = {
  job_id: "batch_1", status: "running", revision: 0, persona_count: 3, completed_personas: 0,
  interviewer_model: "cheap-a", interviewee_model: "cheap-b", turn_limit: 8, estimated_cost_usd: ".009",
  session_usage: { cost_usd: "0" }, transcripts: [], error: null,
};

test("page sends slider and models, locks activities, displays completed batch and starting estimate", async () => {
  const ui = harness(); await ui.settle();
  ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!.props.onChange({ target: { value: "5" } });
  ui.nodes().find(n => n.props["aria-label"] === "Interviewee model")!.props.onChange({ target: { value: "cheap-b" } });
  ui.render();
  let advance!: (value: any) => void;
  ui.setTransport(async (path) => path === "batches" ? { batch: { ...batch, persona_count: 5 } } : new Promise(resolve => { advance = resolve; }));
  const running = ui.button("Run AI-to-AI batch").props.onClick();
  await ui.settle();
  assert.equal(ui.calls[0].payload.persona_count, 5);
  assert.equal(ui.calls[0].payload.interviewer_model, "cheap-a");
  assert.equal(ui.calls[0].payload.interviewee_model, "cheap-b");
  assert.equal(ui.button("neo-002").props.disabled, true);
  assert.equal(ui.button("Ask").props.disabled, true);
  assert.match(ui.text(), /0\/5 personas complete/);
  advance({ batch: { ...batch, status: "completed", completed_personas: 5, persona_count: 5, revision: 80,
    session_usage: { cost_usd: ".003" }, transcripts: [{ persona_id: "neo-001", messages: [{ role: "assistant", content: "Saved batch answer" }] }] } });
  await running; await ui.settle();
  assert.match(ui.text(), /Saved batch answer/);
  assert.match(ui.text(), /Measured cost: \$0.003000 · Estimate at start: \$0.0090/);
  assert.equal(ui.memory.get("interview-batch:std_1"), "batch_1");
});

test("page renders a named batch cap with completed transcripts and allows recovery after network loss", async () => {
  const ui = harness(); await ui.settle();
  let attempt = 0;
  ui.setTransport(async path => {
    if (path === "batches" || path === "batches/batch_1") return { batch };
    if (attempt++ === 0) throw new Error("Network interrupted");
    return { batch: { ...batch, status: "budget_stopped", revision: 17, completed_personas: 1,
      session_usage: { cost_usd: ".018" }, transcripts: [{ persona_id: "neo-001", messages: [{ role: "assistant", content: "Retained answer" }] }],
      error: { code: "quota_exceeded", message: "Budget hard stop", details: { scope: "class" } } } };
  });
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Network interrupted/);
  await ui.button("Resume batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls[2].path, "batches/batch_1");
  assert.match(ui.text(), /Budget stop/);
  assert.match(ui.text(), /class cap: Budget hard stop/);
  assert.match(ui.text(), /Retained answer/);
});

test("chat regeneration preserves failed answer, retries consumed version, updates history and export, and blocks earlier answers", async () => {
  const ui = harness(); await ui.settle();
  await ui.button("Ask").props.onClick(); await ui.settle();
  let attempt = 0;
  ui.setTransport(async () => {
    if (attempt++ === 0) throw new InterviewOperationError("Provider unavailable", 503, { answer_id: "ans_1", version: 1, retry_required: true });
    return { answer: { answer_id: "ans_1", version: 1, reply: "Fresh answer", session_usage: { cost_usd: ".002" } } };
  });
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Original 1/);
  assert.equal(ui.button("Regenerate answer (paid)").props.disabled, false);
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Fresh answer/);
  assert.equal(ui.calls[0].payload.version, 0);
  assert.equal(ui.calls[1].payload.version, 1);
  assert.equal(ui.calls[1].payload.retry, true);
  const exportButton = ui.nodes().find(n => n.type === "Button" && JSON.stringify(n.props.children).includes("Markdown"));
  assert.ok(exportButton);
  await exportButton.props.onClick(); await ui.settle();
  assert.equal(ui.exportedTranscript.turns.at(-1).text, "Fresh answer");
  ui.nodes().find(n => n.props.placeholder === "Ask a follow-up…")!.props.onChange({ target: { value: "Why?" } });
  ui.render();
  await ui.button("Ask").props.onClick(); await ui.settle();
  assert.equal(ui.chatCalls[1].messages.at(-1).content, "Fresh answer");
  const controls = ui.nodes().filter(n => n.type === "Button" && n.props.children === "Regenerate answer (paid)");
  assert.equal(controls.length, 1);
});

test("comparison card regeneration replaces only the selected answer and refreshes its score", async () => {
  const ui = harness(); await ui.settle();
  await ui.button("Compare").props.onClick(); await ui.settle();
  ui.setTransport(async path => {
    assert.equal(path, "answers/card_a/regenerate");
    return { answer: { version: 1, reply: "Changed card A", session_usage: { cost_usd: ".003" },
      post_interview_score: { fit_tier: "strong", emotional_classification: "positive" } } };
  });
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Changed card A/);
  assert.match(ui.text(), /Card B/);
  assert.match(ui.text(), /fit tier: strong/);
  assert.match(ui.text(), /emotion: positive/);
});

test("comparison quota response keeps its completed card visible and regeneratable", async () => {
  const ui = harness([], async () => ({
    ok: false, status: 429,
    json: async () => ({ error: {
      code: "quota_exceeded", message: "Class budget hard stop.",
      details: { results: [{ model_id: "cheap-a", answer_id: "paid_card", version: 0,
        answer: "Completed before stop", error: null }] },
    } }),
  }));
  await ui.settle();
  await ui.button("Compare").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Completed before stop/);
  assert.match(ui.text(), /Class budget hard stop/);
  assert.equal(ui.nodes().filter(n => n.type === "Button" && n.props.children === "Regenerate answer (paid)").length, 1);
  ui.setTransport(async (path, payload) => {
    assert.equal(path, "answers/paid_card/regenerate");
    assert.equal(payload.version, 0);
    return { answer: { version: 1, reply: "Fresh card", session_usage: { cost_usd: ".003" },
      post_interview_score: { fit_tier: "strong", emotional_classification: "positive" } } };
  });
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Fresh card/);
  assert.match(ui.text(), /Class budget hard stop/);
});

test("classroom identity proxy allows batch creation, progress and regeneration without opening workflow runs", () => {
  for (const [method, suffix] of [["GET", "batches"], ["POST", "batches"], ["GET", "batches/batch_1"], ["POST", "batches/batch_1/advance"], ["POST", "answers/ans_1/regenerate"]]) {
    assert.equal(isClassroomInterviewApiRequest(`/api/backend/api/v1/studies/std_1/interview/${suffix}`, method), true);
  }
  assert.equal(isClassroomInterviewApiRequest("/api/backend/api/v1/studies/std_1/interview/runs", "POST"), false);
});


test("rejected batch creation lets corrected settings start without clearing storage", async () => {
  const ui = harness(); await ui.settle();
  ui.setTransport(async () => { throw new InterviewOperationError("Invalid settings", 400); });
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.equal(ui.memory.has("interview-batch-request:std_1"), false);
  ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!.props.onChange({ target: { value: "5" } });
  ui.render();
  ui.setTransport(async () => ({ batch: { ...batch, status: "completed", persona_count: 5 } }));
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls[1].payload.persona_count, 5);
  assert.notEqual(ui.calls[1].payload.request_id, ui.calls[0].payload.request_id);
  assert.match(ui.text(), /completed: 0\/5/);
});

test("ambiguous creation failure retains request identity for recovery", async () => {
  const ui = harness(); await ui.settle();
  ui.setTransport(async () => { throw new Error("Network lost"); });
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.ok(ui.memory.has("interview-batch-request:std_1"));
  ui.setTransport(async () => ({ batch: { ...batch, status: "completed" } }));
  // The room is part of the settings being re-authorized, so the label names it.
  assert.match(ui.text(), /Recover earlier request: 3 personas \(first 3\) · interviewer cheap-a · interviewee cheap-a · expensive models disabled/);
  await ui.button("Recover earlier request").props.onClick(); await ui.settle();
  assert.deepEqual(ui.calls[1].payload, ui.calls[0].payload);
});


test("Run after ambiguous creation posts the currently displayed configuration", async () => {
  const ui = harness(); await ui.settle();
  const count = () => ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!;
  const model = (label: string) => ui.nodes().find(n => n.props["aria-label"] === label)!;
  const optIn = () => ui.nodes().find(n => n.type === "input" && n.props.type === "checkbox")!;
  optIn().props.onChange({ target: { checked: true } }); ui.render();
  model("Interviewer model").props.onChange({ target: { value: "expensive-a" } });
  model("Interviewee model").props.onChange({ target: { value: "expensive-a" } });
  count().props.onChange({ target: { value: "30" } }); ui.render();
  // Fetch rejects before reaching the server; the client cannot know that.
  ui.setTransport(async () => { throw new TypeError("Failed to fetch"); });
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls[0].payload.allow_expensive_models, true);
  assert.equal(ui.calls[0].payload.persona_count, 30);
  assert.equal(ui.calls[0].payload.interviewer_model, "expensive-a");
  assert.equal(ui.calls[0].payload.interviewee_model, "expensive-a");
  assert.equal(optIn().props.disabled, false);
  optIn().props.onChange({ target: { checked: false } });
  count().props.onChange({ target: { value: "3" } }); ui.render();
  model("Interviewee model").props.onChange({ target: { value: "cheap-b" } }); ui.render();
  assert.equal(model("Interviewer model").props.value, "cheap-a");
  assert.equal(model("Interviewee model").props.value, "cheap-b");
  assert.equal(count().props.value, 3);
  assert.equal(optIn().props.checked, false);
  ui.setTransport(async () => ({ batch: { ...batch, status: "completed" } }));
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls[1].path, "batches");
  assert.deepEqual(ui.calls[1].payload, {
    request_id: ui.calls[1].payload.request_id,
    persona_count: 3, interviewer_model: "cheap-a", interviewee_model: "cheap-b",
    allow_expensive_models: false,
  });
  assert.notEqual(ui.calls[1].payload.request_id, ui.calls[0].payload.request_id);
});

test("returning student can reopen completed and paused batches and keep them after another run", async () => {
  const completed = { ...batch, status: "completed", session_usage: { cost_usd: ".048" },
    transcripts: [{ persona_id: "neo-001", messages: [{ role: "assistant", content: "Older saved answer" }] }] };
  const paused = { ...batch, job_id: "batch_2", revision: 1 };
  const ui = harness([paused, completed]); await ui.settle();
  const select = () => ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!;
  select().props.onChange({ target: { value: "batch_1" } }); ui.render();
  assert.match(ui.text(), /Older saved answer/);
  assert.match(ui.text(), /Measured cost: \$0.048000/);
  select().props.onChange({ target: { value: "batch_2" } }); ui.render();
  assert.equal(ui.button("Resume batch").props.disabled, false);
  ui.setTransport(async () => ({ batch: { ...batch, job_id: "batch_3", status: "completed" } }));
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  select().props.onChange({ target: { value: "batch_1" } }); ui.render();
  assert.match(ui.text(), /Older saved answer/);
});


test("failed batch stops automatically and only Resume sends an explicit retry", async () => {
  const ui = harness(); await ui.settle();
  const failed = { ...batch, status: "failed", revision: 1,
    error: { code: "provider_unavailable", message: "Response lost; retrying can incur another charge." } };
  ui.setTransport(async (path, payload) => {
    if (path === "batches") return { batch };
    if (path === "batches/batch_1") return { batch: failed };
    if (payload.retry) return { batch: { ...failed, status: "completed", revision: 2 } };
    return { batch: failed };
  });
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls.length, 2);
  assert.equal(ui.calls[1].payload.retry, false);
  assert.match(ui.text(), /retrying can incur another charge/);
  await ui.button("Resume batch").props.onClick(); await ui.settle();
  assert.deepEqual(ui.calls[3].payload, { revision: 1, retry: true });
});


test("pause confirms after current call, preserves result and cost, and waits for Resume", async () => {
  const ui = harness(); await ui.settle();
  let complete!: (value: any) => void;
  const saved = { ...batch, revision: 1, session_usage: { cost_usd: ".001" },
    transcripts: [{ persona_id: "neo-001", messages: [{ role: "user", content: "Completed current call" }] }] };
  ui.setTransport(async path => path === "batches" ? { batch } : new Promise(resolve => { complete = resolve; }));
  const running = ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  ui.button("Pause after this call").props.onClick(); ui.render();
  assert.match(ui.text(), /Pausing after current call/);
  assert.equal(ui.button("Resume batch").props.disabled, true);
  assert.equal(ui.button("Pause after this call").props.disabled, true);
  complete({ batch: saved }); await running; await ui.settle();
  assert.match(ui.text(), /Paused — select Resume batch to continue/);
  assert.match(ui.text(), /Completed current call/);
  assert.match(ui.text(), /Measured cost: \$0.001000/);
  assert.equal(ui.calls.length, 2);
  await ui.settle(); assert.equal(ui.calls.length, 2);
  ui.setTransport(async path => ({ batch: path.endsWith("advance") ? { ...saved, status: "completed" } : saved }));
  await ui.button("Resume batch").props.onClick(); await ui.settle();
  assert.equal(ui.calls[3].payload.revision, 1);
  assert.match(ui.text(), /completed:/);
});


test("chat budget transport preserves committed follow-up and only offers latest regeneration", async () => {
  const ui = harness(); await ui.settle();
  await ui.button("Ask").props.onClick(); await ui.settle();
  ui.nodes().find(n => n.props.placeholder === "Ask a follow-up…")!.props.onChange({ target: { value: "Why?" } });
  ui.render();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: "quota_exceeded", message: "Run budget stop", details: { scope: "run",
    committed_answer: { session_id: "ses_1", reply: "Paid follow-up", answer_id: "ans_2", version: 0 },
  } } }), { status: 429 });
  ui.api.sendInterviewChatMessage = (_id, payload) => sendInterviewChatMessage(_id, payload) as any;
  try { await ui.button("Ask").props.onClick(); await ui.settle(); }
  finally { globalThis.fetch = originalFetch; }
  assert.match(ui.text(), /Original 1[\s\S]*Why\?[\s\S]*Paid follow-up/);
  assert.match(ui.text(), /Run budget stop/);
  const controls = ui.nodes().filter(n => n.type === "Button" && n.props.children === "Regenerate answer (paid)");
  assert.equal(controls.length, 1);
  ui.setTransport(async () => ({ answer: { answer_id: "ans_2", version: 1, reply: "Fresh" } }));
  await controls[0].props.onClick();
  assert.match(ui.calls.at(-1)!.path, /answers\/ans_2\/regenerate/);
});

for (const status of ["completed", "budget_stopped"] as const) {
  test(`batch ${status} downloads preserve attribution and partial questions`, async () => {
    const saved = { ...batch, status, transcripts: [{ persona_id: "neo-001", messages: [
      { role: "user" as const, content: 'Why, "this"?\nNext line' },
      { role: "assistant" as const, content: "My answer" },
      { role: "user" as const, content: "Unanswered question" },
    ] }] };
    const ui = harness([saved]); await ui.settle();
    ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: saved.job_id } });
    ui.render();
    await ui.button("Download batch CSV").props.onClick();
    // Renamed to match the focus group: the Markdown now carries the memo, not just
    // the transcript, which is what a student actually hands in.
    await ui.button("Export transcript + memo").props.onClick();
    const csv = await batchExport(saved, "csv").blob.text();
    assert.match(csv, /"neo-001","cheap-a","cheap-b","1","Question","Why, ""this""\?\nNext line"/);
    assert.match(csv, /"2","Question","Unanswered question"/);
    const md = await batchExport(saved, "md").blob.text();
    assert.match(md, /neo-001 — Turn 1: Answer/);
    assert.match(md, /Interviewer: cheap-a · Interviewee: cheap-b/);
    assert.match(md, /My answer/);
    assert.match(md, /Unanswered question/);
    // No memo saved yet: a transcript-only export, with no empty Memo heading dangling.
    assert.doesNotMatch(md, /# Memo/);
  });
}

// Refuter round 5, F1: model output lands in a spreadsheet cell. A leading = + - @
// makes that cell a formula, so provider-controlled text would execute on open.
test("batch CSV export neutralises formula-leading interview text", async () => {
  const hostile = { ...batch, status: "completed" as const, transcripts: [{ persona_id: "neo-001", messages: [
    { role: "user" as const, content: "=1+1" },
    { role: "assistant" as const, content: "@SUM(A1:A9)" },
    { role: "user" as const, content: "+1234567890" },
    { role: "assistant" as const, content: "-2+3" },
    { role: "user" as const, content: "A normal question?" },
  ] }] };
  const csv = await batchExport(hostile, "csv").blob.text();

  for (const dangerous of ["=1+1", "@SUM(A1:A9)", "+1234567890", "-2+3"]) {
    assert.ok(
      csv.includes(`"'${dangerous}"`),
      `${dangerous} must be exported as literal text, not a live formula`
    );
    assert.ok(
      !csv.includes(`"${dangerous}"`),
      `${dangerous} must never appear as a bare cell a spreadsheet would evaluate`
    );
  }
  // Ordinary text is untouched — the guard must not corrupt every transcript.
  assert.ok(csv.includes('"A normal question?"'));
});

test("classroom themes proxy permits GET and POST, rejects unsafe paths", () => {
  const path = "/api/backend/api/v1/studies/std_1/interview/batches/batch_1/themes";
  assert.equal(isClassroomInterviewApiRequest(path, "GET"), true);
  assert.equal(isClassroomInterviewApiRequest(path, "POST"), true);
  assert.equal(isClassroomInterviewApiRequest(path, "DELETE"), false);
  assert.equal(isClassroomInterviewApiRequest(path.replace("batch_1", "%2f"), "POST"), false);
});

test("classroom batch confirmation names exact settings and cancellation spends nothing", async () => {
  const ui = harness(); await ui.settle();
  ui.dismissConfirmation();
  await ui.button("Run AI-to-AI batch").props.onClick();
  assert.equal(ui.calls.length, 0);
  assert.match(ui.confirmations[0], /3 personas/);
  assert.match(ui.confirmations[0], /Interviewer: cheap-a/);
  assert.match(ui.confirmations[0], /Interviewee: cheap-a/);
  assert.match(ui.confirmations[0], /\$0\.006/);
});

test("classroom steps preserve settings and expose back navigation", async () => {
  const ui = harness(); await ui.settle();
  assert.equal(ui.nodes().filter(n => n.type === "GlassPanel" && !n.props.hidden).length, 2);
  ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!.props.onChange({ target: { value: "7" } });
  ui.button("Continue").props.onClick(); ui.render();
  assert.ok(ui.nodes().some(n => n.props["aria-current"] === "step"));
  ui.button("Back").props.onClick(); ui.render();
  assert.equal(ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!.props.value, 7);
  assert.equal(ui.calls.length, 0);
});

const themeView = {
  from_run_id: "batch_1", revision: "rev1", eligible: true, available: false, stale: false,
  estimated_cost_usd: ".002", model: "openai/gpt-4o-mini", message: "Ready", saved: null,
};

test("a recruited room is the personas the student ticked, in the order they ticked them", async () => {
  const ui = harness(); await ui.settle();
  // Nobody recruited: the run is still the slider's first N, with no ids sent.
  assert.match(ui.text(), /No one picked/);
  ui.nodes().find(n => n.props.id === "ai-interview-persona-count")!.props.onChange({ target: { value: "7" } });
  ui.render();
  const sliderPrice = ui.text().match(/This run will cost about (.*?)For 7 personas/)![1];
  for (const id of ["neo-003", "neo-001", "neo-002"]) {
    ui.nodes().find(n => n.props["aria-label"] === `Recruit ${id}`)!.props.onChange();
    ui.render();
  }
  assert.match(ui.text(), /Interviewing the 3 you picked: neo-003, neo-001, neo-002/);
  assert.match(ui.text(), /Run AI-to-AI batch \(3 personas\)/);
  // The quote and the sentence under it have to describe the same room, or the
  // student authorizes the slider's price for a room they did not pick.
  const roomPrice = ui.text().match(/This run will cost about (.*?)For 3 personas/)![1];
  assert.notEqual(roomPrice, sliderPrice);
  ui.setTransport(async () => ({ batch: { ...batch, status: "completed", persona_count: 3 } }));
  await ui.button("Run AI-to-AI batch").props.onClick(); ui.render();
  assert.deepEqual(ui.calls[0].payload.persona_ids, ["neo-003", "neo-001", "neo-002"]);
  assert.equal(ui.calls[0].payload.persona_count, 3);
});

test("a room smaller than the minimum cannot be run", async () => {
  const ui = harness(); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Recruit neo-001")!.props.onChange();
  ui.render();
  assert.match(ui.text(), /Pick 2 more/);
  assert.equal(ui.button("Run AI-to-AI batch").props.disabled, true);
  // Unticking puts the slider's room back, so the student is never stuck.
  ui.nodes().find(n => n.props["aria-label"] === "Recruit neo-001")!.props.onChange();
  ui.render();
  assert.equal(ui.button("Run AI-to-AI batch").props.disabled, false);
});

test("classroom themes require separate charge confirmation and navigation never generates", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  assert.equal(ui.calls.length, 0);
  ui.setTransport(async (_path, payload) => ({ insights: payload ? {
    ...themeView, available: true, saved: { revision: "rev1", attempt: 1, themes: [{
      label: "Space", synthesis: "Needs space", representative_quote: "More space", quote_persona_id: "neo-001", sentiment: "positive",
    }] },
  } : themeView }));
  await ui.button("Check saved themes").props.onClick(); ui.render();
  assert.equal(ui.calls[0].payload, undefined);
  await ui.button("Generate themes").props.onClick(); ui.render();
  assert.equal(ui.calls[1].payload.authorize_charge, true);
  assert.equal(ui.calls[1].payload.revision, "rev1");
  assert.match(ui.confirmations[0], /additional cost: \$0.0020/);
  assert.match(ui.text(), /More space/);
  ui.button("Back").props.onClick(); ui.render();
  ui.button("3. Themes").props.onClick(); ui.render();
  assert.equal(ui.calls.length, 2);
  assert.match(ui.text(), /More space/);
});

test("a stale memo is left out of the export instead of riding a newer transcript", async () => {
  // The on-screen memo is warned about; the handed-in file has no warning to carry, so a
  // memo validated against an older revision must not be written next to this transcript.
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  const saved = { revision: "rev0", attempt: 1, themes: [{
    label: "Space", synthesis: "Needs space", representative_quote: "More space",
    quote_persona_id: "neo-001", sentiment: "positive",
  }] };
  ui.setTransport(async () => ({ insights: { ...themeView, available: true, stale: true, saved } }));
  await ui.button("Check saved themes").props.onClick(); ui.render();
  await ui.button("Export transcript + memo").props.onClick();
  assert.equal(ui.exportedMemos[0], undefined);

  const fresh = harness([{ ...batch, status: "completed" }]); await fresh.settle();
  fresh.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  fresh.button("3. Themes").props.onClick(); fresh.render();
  fresh.setTransport(async () => ({ insights: { ...themeView, available: true, saved } }));
  await fresh.button("Check saved themes").props.onClick(); fresh.render();
  await fresh.button("Export transcript + memo").props.onClick();
  assert.equal(fresh.exportedMemos[0], saved);
});

test("a rejected extraction shows no surprise and no options on the page", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.setTransport(async () => ({ insights: { ...themeView, available: false, saved: {
    revision: "rev1", attempt: 1, themes: null, message: "Rejected",
    surprise: { summary: "A surprise", quote: "q", quote_persona_id: "neo-001" },
    answer_options: [{ text: "an option", quote_persona_id: "neo-001" }],
  } } }));
  await ui.button("Check saved themes").props.onClick(); ui.render();
  assert.match(ui.text(), /Rejected/);
  // The student's own memo form always renders, so the check is on the model's
  // section: its heading, its summary text and its quote must all be absent.
  assert.doesNotMatch(ui.text(), /What the model found/);
  assert.doesNotMatch(ui.text(), /A surprise/);
  assert.doesNotMatch(ui.text(), /an option/);
});

test("the memo a student is part way through survives a reload, and stays with its batch", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.nodes().find(n => n.props["aria-label"] === "Your themes")!
    .props.onChange({ target: { value: "People want quiet" } });
  ui.nodes().find(n => n.props["aria-label"] === "Your answer option 1")!
    .props.onChange({ target: { value: "a door I can close" } });
  ui.render();
  assert.equal(JSON.parse(ui.memory.get("interview-memos")!).batch_1.themes, "People want quiet");

  // A fresh mount is what a reload is: the writing has to still be in the fields.
  const reloaded = harness([{ ...batch, status: "completed" }], undefined, ui.memory);
  await reloaded.settle();
  reloaded.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  reloaded.button("3. Themes").props.onClick(); reloaded.render();
  assert.equal(reloaded.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.value,
    "People want quiet");
  assert.equal(reloaded.nodes().find(n => n.props["aria-label"] === "Your answer option 1")!.props.value,
    "a door I can close");
  // And the export carries it, which the mock can only see if the page passes it.
  await reloaded.button("Export transcript + memo").props.onClick();
  assert.equal(reloaded.exportedStudentMemos[0].themes, "People want quiet");

  // A different batch is a different analysis: it starts blank and exports nothing.
  const other = harness([{ ...batch, job_id: "batch_2", status: "completed" }], undefined, ui.memory);
  await other.settle();
  other.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_2" } });
  other.button("3. Themes").props.onClick(); other.render();
  assert.equal(other.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.value, "");
  await other.button("Export transcript + memo").props.onClick();
  assert.equal(other.exportedStudentMemos[0], undefined);
});

test("a stored memo of the wrong shape is dropped, not exported", async () => {
  // The store is reachable by an older build, another tab and the devtools, so a
  // non-string option must not reach the export and throw there.
  const poisoned = new Map<string, string>([["interview-memos", JSON.stringify({
    batch_1: { themes: "kept", surprise: "", options: ["fine"] },
    batch_2: { themes: "dropped", surprise: "", options: [7] },
  })]]);
  const ui = harness([{ ...batch, status: "completed" }, { ...batch, job_id: "batch_2", status: "completed" }],
    undefined, poisoned);
  await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_2" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  assert.equal(ui.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.value, "");
});

test("the memo form is inert until a batch is chosen, and says so", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.button("3. Themes").props.onClick(); ui.render();
  // Live-looking fields that discard keystrokes are how a student loses their memo.
  assert.equal(ui.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.disabled, true);
  assert.match(ui.text(), /Select a batch first/);
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.render();
  assert.equal(ui.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.disabled, false);
  assert.doesNotMatch(ui.text(), /Select a batch first/);
});

test("a browser that refuses to save the memo says so while the text is still there", async () => {
  // Safari private browsing throws on setItem; a silent swallow means the student
  // finds out only after the reload that already destroyed their writing.
  class Blocked extends Map<string, string> {
    // Only the memo store is refused, so the test exercises that write and not the
    // page's unrelated saved-batch bookkeeping.
    set(key: string, value: string) {
      if (key === "interview-memos") throw new Error("QuotaExceededError");
      return super.set(key, value);
    }
  }
  const ui = harness([{ ...batch, status: "completed" }], undefined, new Blocked());
  await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.nodes().find(n => n.props["aria-label"] === "Your themes")!
    .props.onChange({ target: { value: "People want quiet" } });
  ui.render();
  assert.match(ui.text(), /not saving your memo/);
  // And the writing is still on screen, which is the whole point of warning now.
  assert.equal(ui.nodes().find(n => n.props["aria-label"] === "Your themes")!.props.value, "People want quiet");
});

test("the reflection is typed in the app, saved with its batch and exported", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.nodes().find(n => n.props["aria-label"] === REFLECTION_PROMPTS[2])!
    .props.onChange({ target: { value: "We rejected its fourth theme." } });
  ui.render();
  // Each prompt writes its own slot; the others stay empty rather than shifting.
  assert.deepEqual(JSON.parse(ui.memory.get("interview-memos")!).batch_1.reflection,
    ["", "", "We rejected its fourth theme.", ""]);
  await ui.button("Export transcript + memo").props.onClick();
  assert.deepEqual(ui.exportedStudentMemos[0].reflection, ["", "", "We rejected its fourth theme.", ""]);
});

test("classroom switching saved runs rejects late themes", async () => {
  const ui = harness([{ ...batch, status: "completed" }, { ...batch, job_id: "batch_2", status: "completed" }]); await ui.settle();
  const select = () => ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!;
  select().props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  let resolve!: (response: any) => void;
  ui.setTransport(async () => new Promise(done => { resolve = done; }));
  const pending = ui.button("Check saved themes").props.onClick();
  await ui.settle();
  assert.equal(select().props.disabled, true);
  select().props.onChange({ target: { value: "batch_2" } });
  resolve({ insights: { ...themeView, message: "Earlier run themes" } });
  await pending; ui.render();
  assert.doesNotMatch(ui.text(), /Earlier run themes/);
});

test("classroom dismissing theme charge preserves transcripts without a POST", async () => {
  const ui = harness([{ ...batch, status: "completed" }]); await ui.settle();
  ui.nodes().find(n => n.props["aria-label"] === "Saved batches")!.props.onChange({ target: { value: "batch_1" } });
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.setTransport(async () => ({ insights: themeView }));
  await ui.button("Check saved themes").props.onClick(); ui.render();
  ui.dismissConfirmation();
  await ui.button("Generate themes").props.onClick(); ui.render();
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.calls[0].payload, undefined);
  assert.match(ui.text(), /Download batch CSV/);
  assert.match(ui.text(), /Export transcript \+ memo/);
});

test("the interview step picks which persona is being interviewed, and keeps the run's models", async () => {
  const ui = harness();
  await ui.settle();
  // The persona list lives in step 0; the student interviews someone in step 1, so the
  // choice has to be reachable from there or every interview is with the first persona.
  ui.nodes()
    .find((node) => node.props["aria-label"] === "Interviewee model")!
    .props.onChange({ target: { value: "cheap-b" } });
  ui.render();
  assert.match(ui.text(), /Interviewing \(neo-001\)/);
  ui.button("neo-003").props.onClick();
  ui.render();
  assert.match(ui.text(), /Interviewing \(neo-003\)/);
  await ui.button("Ask").props.onClick();
  await ui.settle();
  assert.equal(ui.chatCalls.at(-1).persona_id, "neo-003");
  // Switching person starts a new conversation; it must not quietly reset the models the
  // student chose for this run.
  assert.equal(
    ui.nodes().find((node) => node.props["aria-label"] === "Interviewee model")!.props.value,
    "cheap-b"
  );
});

test("switching persona mid-interview asks first, and a declined switch keeps the transcript", async () => {
  const ui = harness();
  await ui.settle();
  await ui.button("Ask").props.onClick();
  await ui.settle();
  assert.match(ui.text(), /Original 1/);
  ui.dismissConfirmation();
  ui.button("neo-002").props.onClick();
  ui.render();
  assert.match(ui.confirmations.at(-1)!, /neo-002/);
  assert.match(ui.text(), /Interviewing \(neo-001\)/, "a declined switch must not change persona");
  assert.match(ui.text(), /Original 1/, "the transcript survives a declined switch");
});

test("an accepted switch clears the interview and keeps the run's models", async () => {
  const ui = harness();
  await ui.settle();
  ui.nodes()
    .find((node) => node.props["aria-label"] === "Interviewee model")!
    .props.onChange({ target: { value: "cheap-b" } });
  ui.render();
  await ui.button("Ask").props.onClick();
  await ui.settle();
  assert.match(ui.text(), /Original 1/);
  // The destructive branch, confirmed: the transcript really does go.
  ui.button("neo-002").props.onClick();
  ui.render();
  assert.match(ui.confirmations.at(-1)!, /Switch to neo-002/);
  assert.match(ui.text(), /Interviewing \(neo-002\)/);
  assert.doesNotMatch(ui.text(), /Original 1/);
  assert.equal(
    ui.nodes().find((node) => node.props["aria-label"] === "Interviewee model")!.props.value,
    "cheap-b",
    "the models chosen for this run survive the switch"
  );
});

test("re-selecting the persona already in the chair is the start-over control, and it asks", async () => {
  const ui = harness();
  await ui.settle();
  await ui.button("Ask").props.onClick();
  await ui.settle();
  assert.match(ui.text(), /Original 1/);
  ui.button("neo-001").props.onClick();
  ui.render();
  assert.match(ui.confirmations.at(-1)!, /Start over with neo-001/);
  assert.doesNotMatch(ui.text(), /Original 1/);
});

test("switching persona drops an expensive comparison model instead of substituting one", async () => {
  const ui = harness();
  await ui.settle();
  // The checkboxes carry no label of their own; flatten() is depth-first, so the first
  // input after a label element is that label's own control.
  const checkboxIn = (labelText: string) => {
    const nodes = ui.nodes();
    const label = nodes.findIndex((node) => {
      if (node.type !== "label") return false;
      // The model <select>s list every model as an <option>, so a name match alone finds
      // the wrong label. Only the checkbox labels are meant here.
      const children = JSON.stringify(node.props.children ?? "");
      return children.includes(labelText) && children.includes('"checkbox"');
    });
    assert.ok(label >= 0, `no label matching ${labelText}`);
    const input = nodes.slice(label).find((node) => node.props.type === "checkbox");
    assert.ok(input, `no checkbox under ${labelText}`);
    return input!;
  };
  checkboxIn("Enable expensive models for this comparison").props.onChange({
    target: { checked: true },
  });
  ui.render();
  checkboxIn("Expensive A").props.onChange({ target: { checked: true } });
  ui.render();
  assert.match(ui.text(), /Models to compare \(3 selected\)/);
  ui.button("neo-002").props.onClick();
  ui.render();
  // Two cheap models remain selected: the expensive one is dropped, not swapped for a
  // default the student never checked, and the set can still run.
  assert.match(ui.text(), /Models to compare \(2 selected\)/);
  assert.equal(checkboxIn("Expensive A").props.checked, false);
});

test("the discard warning names every artifact the click destroys", async () => {
  const ui = harness();
  await ui.settle();
  await ui.button("Ask").props.onClick();
  await ui.settle();
  ui.setTransport(async () => ({}));
  await ui.button("Compare 2 models").props.onClick();
  await ui.settle();
  ui.dismissConfirmation();
  ui.button("neo-002").props.onClick();
  ui.render();
  const warning = ui.confirmations.at(-1)!;
  assert.match(warning, /interview message/);
  assert.match(warning, /compared model answer/, "the paid comparison answers go too");
});

test("the interview step carries its own copy of the persona list, and it switches", async () => {
  const ui = harness();
  await ui.settle();
  const named = (id: string) =>
    ui.nodes().filter(
      (node) => node.type === "button" && JSON.stringify(node.props.children ?? "").includes(id)
    );
  assert.equal(
    named("neo-002").length,
    2,
    "one list in the choose step, one in the interview step"
  );
  // Click the interview step's copy specifically, not the one this page always had.
  named("neo-002")[1].props.onClick();
  ui.render();
  assert.match(ui.text(), /Interviewing \(neo-002\)/);
});

test("a persona switch cannot land while the transcript export it advises is still running", async () => {
  const ui = harness();
  await ui.settle();
  await ui.button("Ask").props.onClick();
  await ui.settle();
  let finishExport!: (value: any) => void;
  ui.api.getInterviewTranscriptExport = () => new Promise((resolve) => { finishExport = resolve; });
  const exportButton = ui
    .nodes()
    .find((node) => node.type === "Button" && JSON.stringify(node.props.children).includes("Markdown"))!;
  const exporting = exportButton.props.onClick();
  await ui.settle();
  const personaButton = ui
    .nodes()
    .find((node) => node.type === "button" && JSON.stringify(node.props.children ?? "").includes("neo-002"))!;
  assert.equal(personaButton.props.disabled, true, "switching is closed while the export is in flight");
  finishExport({ blob: new Blob(["t"]), filename: "t.md" });
  await exporting;
  await ui.settle();
  assert.match(ui.text(), /Original 1/);
});

test("demo mode page opens prerecorded batch without models, disables run, exports and never pays", async () => {
  const ui = harness([], undefined, undefined, true);
  await ui.settle();
  assert.deepEqual(ui.calls.map(c => c.path), ["demo/batch"]);
  assert.match(ui.text(), /6\/6 personas complete/);
  assert.match(ui.text(), /Measured cost: \$0.000000/);
  assert.equal(ui.button("Run AI-to-AI batch").props.disabled, true);
  // Calling the handler directly is also refused, independent of disabled markup.
  await ui.button("Run AI-to-AI batch").props.onClick();
  ui.button("Export transcript + memo").props.onClick();
  assert.equal(ui.calls.length, 1);
  assert.equal(ui.chatCalls.length, 0);
  ui.button("3. Themes").props.onClick(); ui.render();
  ui.setTransport(async () => ({ insights: { from_run_id: "demo_batch", eligible: false, available: false,
    saved: null, message: "No themes were saved in this demo." } }));
  await ui.button("Check saved themes").props.onClick(); await ui.settle();
  assert.match(ui.text(), /No themes were saved/);
  assert.equal(ui.nodes().some(n => n.type === "Button" && String(n.props.children).includes("Generate themes")), false);
});

test("demo switch during live advance retains its paid result and stops further automatic calls", async () => {
  const ui = harness(); await ui.settle();
  let complete!: (value: any) => void;
  ui.setTransport(async path => path === "batches" ? { batch } : new Promise(resolve => { complete = resolve; }));
  const running = ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  ui.setDemo(true);
  complete({ batch: { ...batch, revision: 1, session_usage: { cost_usd: ".001" },
    transcripts: [{ persona_id: "neo-001", messages: [{ role: "user", content: "Paid live result preserved" }] }] } });
  await running; await ui.settle();
  assert.equal(ui.calls.length, 2);
  assert.match(ui.text(), /Paid live result preserved/);
  ui.setDemo(false); await ui.settle();
  assert.equal(ui.calls.length, 2, "turning demo off cannot resume paid work automatically");
  assert.equal(ui.button("Resume batch").props.disabled, false);
});
