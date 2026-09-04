import test from "node:test";
import assert from "node:assert/strict";

import {
  formatInterviewModelOption,
  isInterviewModelSelectable,
  resetExpensiveModelSelection,
} from "../src/lib/interview-models";
import type { InterviewModelCatalogEntry } from "../src/lib/api";


const cheap: InterviewModelCatalogEntry = {
  id: "provider/cheap",
  name: "Cheap Model",
  tier: "cheap",
  prompt_price_per_million: 0.1,
  completion_price_per_million: 0.4,
};

const expensive: InterviewModelCatalogEntry = {
  id: "provider/expensive",
  name: "Expensive Model",
  tier: "expensive",
  prompt_price_per_million: 3,
  completion_price_per_million: 15,
};


test("model option labels show tier and both real per-million prices", () => {
  assert.equal(
    formatInterviewModelOption(cheap),
    "Cheap · Cheap Model · $0.10 in / $0.40 out per 1M tokens"
  );
});


test("expensive models require opt-in while cheap models remain selectable", () => {
  assert.equal(isInterviewModelSelectable(cheap, false), true);
  assert.equal(isInterviewModelSelectable(expensive, false), false);
  assert.equal(isInterviewModelSelectable(expensive, true), true);
});


test("ending expensive opt-in resets only an expensive selection", () => {
  const models = [cheap, expensive];
  assert.equal(
    resetExpensiveModelSelection(models, expensive.id, cheap.id),
    cheap.id
  );
  assert.equal(
    resetExpensiveModelSelection(models, cheap.id, cheap.id),
    cheap.id
  );
});
