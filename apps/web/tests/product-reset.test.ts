import test from "node:test";
import assert from "node:assert/strict";

import { describeProductReset } from "../src/lib/product-reset";

/**
 * F-16. Reset clears the form. It does not call the API, and the flag that suppresses re-seeding is
 * component state, so a reload restores the saved product. The message claimed the opposite:
 * "Neo content will not return unless you load the demo examples."
 */

test("with a saved product, the message says the saved copy is untouched", () => {
  const outcome = describeProductReset({ hasSavedProduct: true });

  assert.match(outcome.message, /saved/i);
  assert.match(outcome.message, /reload|refresh/i, "a reload is what brings it back");
  assert.equal(outcome.tone, "warning");
});

test("no message claims the cleared content will not come back", () => {
  for (const hasSavedProduct of [true, false]) {
    const outcome = describeProductReset({ hasSavedProduct });
    assert.ok(
      !/will not return/i.test(outcome.message),
      `still claims the content will not return: ${outcome.message}`
    );
  }
});

test("with nothing saved, the message does not warn about a saved copy that does not exist", () => {
  const outcome = describeProductReset({ hasSavedProduct: false });

  assert.ok(
    !/reload|refresh/i.test(outcome.message),
    `there is nothing to come back: ${outcome.message}`
  );
  assert.match(outcome.message, /save when ready/i);
});

test("the message tells the reader how to make the change stick", () => {
  const outcome = describeProductReset({ hasSavedProduct: true });
  assert.match(outcome.message, /save/i);
});
