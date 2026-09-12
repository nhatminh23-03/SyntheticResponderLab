import test from "node:test";
import assert from "node:assert/strict";

import {
  canOpenCompactAppMenu,
  standaloneAppLinks,
} from "../src/lib/app-navigation";
import { workflowSections } from "../src/lib/workflow-sections";

test("student interview is a standalone app destination outside the study workflow", () => {
  assert.deepEqual(standaloneAppLinks, [
    { href: "/interview", label: "Student Interview" },
  ]);
  assert.equal(
    workflowSections.some((section) => section.id === ("interview" as string)),
    false
  );
});

test("compact app menu remains openable for standalone destinations during a workflow lock", () => {
  assert.equal(canOpenCompactAppMenu(true, standaloneAppLinks.length), true);
  assert.equal(canOpenCompactAppMenu(true, 0), false);
});
