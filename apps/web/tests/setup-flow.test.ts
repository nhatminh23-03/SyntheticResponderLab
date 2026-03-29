import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStudyModeStatusMessage,
  resolveSetupSeedSource,
} from "../src/lib/setup-flow-utils";

test("resolveSetupSeedSource prioritizes saved backend state", () => {
  assert.equal(
    resolveSetupSeedSource({ sectionStatus: "saved", studyMode: "neo_smart" }),
    "saved"
  );
  assert.equal(
    resolveSetupSeedSource({ sectionStatus: "saved", studyMode: "general" }),
    "saved"
  );
});

test("resolveSetupSeedSource returns neo defaults only when section is unsaved in neo mode", () => {
  assert.equal(
    resolveSetupSeedSource({ sectionStatus: "not_started", studyMode: "neo_smart" }),
    "neo_default"
  );
  assert.equal(
    resolveSetupSeedSource({ sectionStatus: "not_started", studyMode: "general" }),
    "empty"
  );
});

test("buildStudyModeStatusMessage explains preserved downstream sections", () => {
  assert.equal(
    buildStudyModeStatusMessage("general", ["Audience", "Product"]),
    "General Custom Study saved. Existing saved setup sections were preserved: Audience, Product."
  );
  assert.equal(
    buildStudyModeStatusMessage("neo_smart", []),
    "Neo Smart Living Demo saved. Continue into Audience setup."
  );
});
