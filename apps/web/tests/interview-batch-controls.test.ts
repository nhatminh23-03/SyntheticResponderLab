import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { InterviewOperationError } from "../src/lib/standalone-interview";
import * as modelHelpers from "../src/lib/interview-models";
import * as comparisonHelpers from "../src/lib/interview-comparison";
import { isClassroomInterviewApiRequest } from "../src/lib/classroom-access";

// Render the actual page with deterministic hooks and transport. This exercises its
// event handlers and rendered controls without a browser or a paid provider.
type Element = { type: unknown; props: Record<string, any> };
function harness(savedBatches: any[] = []) {
  const states: any[] = [];
  let cursor = 0;
  const effects: (() => void)[] = [];
  let first = true;
  const calls: { path: string; payload: any }[] = [];
  const chatCalls: any[] = [];
  const models = [
    { id: "cheap-a", name: "A", tier: "cheap", prompt_price_per_million: 0.1, completion_price_per_million: 0.2, estimated_cost_per_persona_usd: .001 },
    { id: "cheap-b", name: "B", tier: "cheap", prompt_price_per_million: 0.2, completion_price_per_million: 0.3, estimated_cost_per_persona_usd: .002 },
  ];
  const personas = ["neo-001", "neo-002", "neo-003"].map(persona_id => ({ persona_id, lifestyle_tags: [], census_profile: "Household" }));
  const memory = new Map<string, string>();
  let transport: (path: string, payload: any) => Promise<any> = async () => { throw new Error("unexpected request"); };
  let exportsPayload: any;
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
    InterviewChatApiError: class extends Error {},
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
    "framer-motion": { AnimatePresence: "presence", motion: { div: "div" } },
    "@/lib/api": api,
    "@/lib/interview-models": modelHelpers,
    "@/lib/interview-comparison": { ...comparisonHelpers, runInterviewComparison: async () => [
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
  for (const [file, component] of [["badge-chip", "BadgeChip"], ["button", "Button"], ["glass-panel", "GlassPanel"]]) {
    mocks[`@/components/ui/${file}`] = { [component]: component };
  }
  const source = readFileSync(resolve(__dirname, "../../src/app/interview/page.tsx"), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exported: any = {};
  const storage = { getItem: (key: string) => memory.get(key) ?? null, setItem: (key: string, value: string) => memory.set(key, value), removeItem: (key: string) => memory.delete(key) };
  const dom = { createElement: () => ({ click() {}, remove() {} }), body: { appendChild() {} } };
  new Function("require", "exports", "localStorage", "document", compiled)((name: string) => mocks[name] ?? require(name), exported, storage, dom);
  const component = exported.default().props.children.type;
  let tree: Element;
  function render() { cursor = 0; tree = component(); first = false; return tree; }
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
    calls, chatCalls, memory,
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

test("chat regeneration preserves failed answer, retries same version, updates history and export, and blocks earlier answers", async () => {
  const ui = harness(); await ui.settle();
  await ui.button("Ask").props.onClick(); await ui.settle();
  let attempt = 0;
  ui.setTransport(async () => {
    if (attempt++ === 0) throw new Error("Provider unavailable");
    return { answer: { answer_id: "ans_1", version: 1, reply: "Fresh answer", session_usage: { cost_usd: ".002" } } };
  });
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Original 1/);
  assert.equal(ui.button("Regenerate answer (paid)").props.disabled, false);
  await ui.button("Regenerate answer (paid)").props.onClick(); await ui.settle();
  assert.match(ui.text(), /Fresh answer/);
  assert.equal(ui.calls[0].payload.version, 0);
  assert.equal(ui.calls[1].payload.version, 0);
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
  await ui.button("Run AI-to-AI batch").props.onClick(); await ui.settle();
  assert.deepEqual(ui.calls[1].payload, ui.calls[0].payload);
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
