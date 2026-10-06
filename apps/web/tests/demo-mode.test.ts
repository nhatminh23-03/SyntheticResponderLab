import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { DEMO_MODE_STORAGE_KEY, isDemoMode, setDemoMode, useDemoMode } from "../src/lib/demo-mode";
import { isClassroomInterviewApiRequest } from "../src/lib/classroom-access";
import { batchExport } from "../src/lib/interview-batch-export";
import { humanInterviewExport } from "../src/lib/human-interview";
import type { Batch } from "../src/lib/standalone-interview";

const read = (path: string) => readFileSync(resolve(__dirname, "../..", path), "utf8");

test("demo switch persists one shared value and broadcasts same-tab changes", () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  const values = new Map<string, string>();
  const target = new EventTarget();
  let updates = 0;
  target.addEventListener("srl-demo-mode-change", () => updates++);
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    localStorage: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value) },
    dispatchEvent: target.dispatchEvent.bind(target),
  }});
  try {
    assert.equal(isDemoMode(), false);
    setDemoMode(true);
    assert.equal(values.get(DEMO_MODE_STORAGE_KEY), "true");
    assert.equal(isDemoMode(), true);
    setDemoMode(false);
    assert.equal(isDemoMode(), false);
    assert.equal(updates, 2);
    assert.equal(typeof useDemoMode, "function");
  } finally {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  }
});

test("demo switch is accessible shared chrome, with cross-tab storage synchronization", () => {
  assert.match(read("src/app/layout.tsx"), /<DemoSwitch \/>/);
  const component = read("src/components/demo/demo-mode.tsx");
  assert.match(component, /role="switch" checked=\{demo\}/);
  assert.match(component, /Demo \(no AI\)/);
  const store = read("src/lib/demo-mode.ts");
  assert.match(store, /addEventListener\("storage", storage\)/);
  assert.match(store, /event.key === DEMO_MODE_STORAGE_KEY/);
});

test("demo mode opens all three fixtures, keeps live state mounted, guards paid actions", () => {
  for (const [page, kind] of [["focus-group", "focus-group"], ["interview", "batch"], ["interview/you", "you"]]) {
    const source = read(`src/app/${page}/page.tsx`);
    assert.match(source, /<DemoScreens>/);
    assert.ok(source.includes(`"demo/${kind}"`));
    assert.match(source, /<DemoNotice/);
    assert.match(source, /readOnly \|\| isDemoMode\(\)/);
    assert.match(source, /if \(!active\) return/);
    assert.match(source, /Retry demo load/);
  }
  const screens = read("src/components/demo/demo-mode.tsx");
  assert.match(screens, /hidden=\{demo\}>\{children\(false\)\}/);
  const batch = read("src/app/interview/page.tsx");
  assert.match(batch, /if \(isDemoMode\(\) \|\| pauseBatch.current/);
  assert.match(batch, /pauseBatch.current = true; setPausing\(true\)/);
  assert.match(batch, /!readOnly && themes.eligible/);
});

test("demo mode allowlist opens only exact demo POST endpoints", () => {
  const prefix = "/api/backend/api/v1/studies/std_123/interview/demo/";
  for (const kind of ["focus-group", "batch", "you"]) {
    assert.ok(isClassroomInterviewApiRequest(prefix + kind, "POST"));
    for (const method of ["GET", "DELETE", "PUT", "PATCH"]) assert.equal(isClassroomInterviewApiRequest(prefix + kind, method), false);
    for (const suffix of ["/ask", "%2fask", "%3f", "/../chat"]) assert.equal(isClassroomInterviewApiRequest(prefix + kind + suffix, "POST"), false);
  }
  assert.equal(isClassroomInterviewApiRequest(prefix + "survey", "POST"), false);
});

test("demo mode batch and human exports retain labels, transcript and zero playback cost", async () => {
  const fixture = JSON.parse(read("../api/seed_data/demo/batch.json"));
  const batch: Batch = { ...fixture.config, ...fixture.state, demo: true, provisional: fixture.provisional,
    job_id: "demo_batch", status: "completed", session_usage: { cost_usd: "0" }, error: null };
  const human = JSON.parse(read("../api/seed_data/demo/you.json"));
  for (const format of ["csv", "md"] as const) {
    for (const [exported, provisional] of [[batchExport(batch, format), fixture.provisional], [humanInterviewExport({ ...human.state, demo: true,
      provisional: human.provisional, sessionId: "you_demo", ended: true, turnLimit: 8, costUsd: "0" }, format), human.provisional]] as const) {
      const text = await exported.blob.text();
      assert.match(text, /Demo session - pre-recorded, no AI/);
      assert.match(text, /Synthetic rehearsal/);
      assert.match(text, /Playback cost: \$0/);
      // The note tracks the fixture flag: shown for hand-written fixtures, absent for real recordings.
      if (provisional) assert.match(text, /Provisional hand-written example/);
      else assert.doesNotMatch(text, /Provisional hand-written example/);
    }
  }
});

test("demo mode keeps demo sessions out of live history", () => {
  const batch = read("src/app/interview/page.tsx");
  assert.match(batch, /batches\.filter\(item => !item\.demo &&/);
  assert.match(batch, /if \(active && !recovered\.demo\) setBatch/);
  assert.match(read("src/app/focus-group/page.tsx"), /setRooms\(result\.rooms\.filter\(\(entry\) => !entry\.demo\)\)/);
});

test("demo mode isolates student photos, custom concepts and browser memo storage", () => {
  const focus = read("src/app/focus-group/page.tsx");
  assert.match(focus, /room.concept_card && !readOnly \? \(/);
  assert.match(focus, /const readOnly = demoPlayback \|\| !!room\?\.demo/);
  assert.doesNotMatch(focus, /localStorage|sessionStorage/);
  const batch = read("src/app/interview/page.tsx");
  assert.match(batch, /if \(!readOnly\) localStorage.setItem\(MEMO_STORE/);
  const screens = read("src/components/demo/demo-mode.tsx");
  assert.match(screens, /key=\{`live:\$\{studyId\}`\}/);
  assert.match(screens, /key=\{`demo:\$\{studyId\}`\}/);
});

test("demo switch native accessible control changes checked state in shared responsive chrome", () => {
  // Exercise the rendered native control and its handler, not a second implementation.
  const ts = require("typescript") as typeof import("typescript");
  let enabled = false;
  const exported: any = {};
  const code = ts.transpileModule(read("src/components/demo/demo-mode.tsx"), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  new Function("require", "exports", code)((name: string) => {
    if (name === "@/lib/demo-mode") return { useDemoMode: () => [enabled, (value: boolean) => { enabled = value; }] };
    if (name === "@/providers/study-provider") return {};
    return require(name);
  }, exported);
  const control = () => {
    const container = exported.DemoSwitch();
    const label = container.props.children;
    assert.equal(label.type, "label");
    assert.ok(label.props.children.includes("Demo (no AI)"));
    assert.doesNotMatch(container.props.className + label.props.className, /hidden/);
    const input = label.props.children[0];
    assert.equal(input.type, "input");
    assert.equal(input.props.type, "checkbox"); // Native Space activation and focus semantics.
    assert.equal(input.props.role, "switch");
    assert.equal(input.props.disabled, undefined);
    assert.equal(input.props.tabIndex, undefined); // Native focus order remains intact.
    return input;
  };
  assert.equal(control().props.checked, false);
  control().props.onChange({ target: { checked: true } });
  assert.equal(control().props.checked, true);
  control().props.onChange({ target: { checked: false } });
  assert.equal(control().props.checked, false);
});

test("demo switch cross-tab subscriber observes storage events and cleans up", () => {
  const ts = require("typescript") as typeof import("typescript");
  const target = new EventTarget();
  const values = new Map<string, string>();
  let subscribe!: (listener: () => void) => () => void;
  const exported: any = {};
  const code = ts.transpileModule(read("src/lib/demo-mode.ts"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  new Function("require", "exports", "window", code)(() => ({
    useSyncExternalStore(sub: typeof subscribe, snapshot: () => boolean) { subscribe = sub; return snapshot(); },
  }), exported, {
    localStorage: { getItem: (key: string) => values.get(key) ?? null },
    addEventListener: target.addEventListener.bind(target), removeEventListener: target.removeEventListener.bind(target),
  });
  exported.useDemoMode();
  const observed: boolean[] = [];
  const unsubscribe = subscribe(() => observed.push(exported.isDemoMode()));
  const storage = (key: string | null) => target.dispatchEvent(Object.assign(new Event("storage"), { key }));
  values.set(DEMO_MODE_STORAGE_KEY, "true");
  storage(DEMO_MODE_STORAGE_KEY);
  storage("unrelated");
  values.clear();
  storage(null);
  assert.deepEqual(observed, [true, false]);
  unsubscribe();
  storage(DEMO_MODE_STORAGE_KEY);
  assert.equal(observed.length, 2);
});
