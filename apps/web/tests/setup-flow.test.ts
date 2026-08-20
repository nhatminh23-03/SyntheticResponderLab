import test from "node:test";
import assert from "node:assert/strict";

import {
  buildStudyModeStatusMessage,
  fromOwnershipFilter,
  resolveSetupSeedSource,
  toOwnershipFilter,
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
    "General Custom Study saved. Kept your saved inputs in: Audience, Product."
  );
  assert.equal(
    buildStudyModeStatusMessage("neo_smart", []),
    "Neo Smart Living Demo saved. Next step: Audience setup."
  );
});

test("toOwnershipFilter maps stored flags onto the single selector", () => {
  assert.equal(
    toOwnershipFilter({ homeowner_only: false, renter_only: false }),
    "any"
  );
  assert.equal(
    toOwnershipFilter({ homeowner_only: true, renter_only: false }),
    "homeowner_only"
  );
  assert.equal(
    toOwnershipFilter({ homeowner_only: false, renter_only: true }),
    "renter_only"
  );
});

test("fromOwnershipFilter never produces the contradictory both-true state", () => {
  for (const value of ["any", "homeowner_only", "renter_only"] as const) {
    const flags = fromOwnershipFilter(value);
    assert.ok(
      !(flags.homeowner_only && flags.renter_only),
      `${value} produced both-true, which the backend rejects`
    );
  }
});

test("ownership selector round-trips every option", () => {
  for (const value of ["any", "homeowner_only", "renter_only"] as const) {
    assert.equal(toOwnershipFilter(fromOwnershipFilter(value)), value);
  }
});

test("any ownership clears both flags so no constraint reaches the sampler", () => {
  assert.deepEqual(fromOwnershipFilter("any"), {
    homeowner_only: false,
    renter_only: false,
  });
});
