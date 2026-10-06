import test from "node:test";
import assert from "node:assert/strict";

import { sectionWindowScrollTop } from "../src/lib/section-scroll";
import { workflowSections } from "../src/lib/workflow-sections";

test("going back to the first section scrolls to the very top, so the app-wide Demo switch above it is visible again", () => {
  // Desktop: the first section starts right under the 41px Demo strip; landing on its top edge (42) hid the strip for good.
  assert.equal(sectionWindowScrollTop(workflowSections[0].id, 42, 0, true), 0);
  assert.equal(sectionWindowScrollTop(workflowSections[0].id, 120, 64, false), 0);
});

test("other sections keep their offset under the sticky nav", () => {
  assert.equal(sectionWindowScrollTop("survey", 4300, 89, true), 4211);
  assert.equal(sectionWindowScrollTop("survey", 4300, 64, false), 4224);
});

test("a section near the top never yields a negative scroll position", () => {
  assert.equal(sectionWindowScrollTop("study-mode", 30, 89, true), 0);
});
