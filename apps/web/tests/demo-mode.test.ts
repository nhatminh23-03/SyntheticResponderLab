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
    for (const exported of [batchExport(batch, format), humanInterviewExport({ ...human.state, demo: true,
      provisional: true, sessionId: "you_demo", ended: true, turnLimit: 8, costUsd: "0" }, format)]) {
      const text = await exported.blob.text();
      assert.match(text, /Demo session - pre-recorded, no AI/);
      assert.match(text, /Synthetic rehearsal/);
      assert.match(text, /Playback cost: \$0/);
      assert.match(text, /Provisional hand-written example/);
    }
  }
});
