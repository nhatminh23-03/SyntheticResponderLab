import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";


const interviewPageSource = readFileSync(
  resolve(__dirname, "../../src/app/interview/page.tsx"),
  "utf8"
);

test("suggested questions populate the free-text box submitted by ask", () => {
  assert.match(
    interviewPageSource,
    /SUGGESTED\.map\(\(suggestion\) => \([\s\S]*?onClick=\{\(\) => setQuestion\(suggestion\)\}[\s\S]*?<\/button>[\s\S]*?\)\)\}/
  );
  assert.match(
    interviewPageSource,
    /<input[\s\S]*?value=\{question\}[\s\S]*?onChange=\{\(event\) => setQuestion\(event\.target\.value\)\}[\s\S]*?if \(event\.key === "Enter"\) ask\(\);[\s\S]*?placeholder="Ask a follow-up…"/
  );
  assert.match(
    interviewPageSource,
    /async function ask\(\) \{[\s\S]*?const asked = question\.trim\(\);[\s\S]*?prompt: asked,/
  );
  assert.match(
    interviewPageSource,
    /<Button[\s\S]*?onClick=\{ask\}[\s\S]*?\{loading \? "Asking…" : "Ask"\}[\s\S]*?<\/Button>/
  );
});

test("persona selection is locked while an interview reply is in flight", () => {
  assert.match(
    interviewPageSource,
    /personas\.map\(\(entry\) => \([\s\S]*?onClick=\{\(\) => selectPersona\(entry\.persona_id\)\}[\s\S]*?disabled=\{loading \|\| comparisonLoading\}/
  );
});
