import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  chapterFor,
  chapterLength,
  formatTime,
  parseVideoParam,
  walkthroughHref,
  type WalkthroughManifest,
} from "../src/lib/walkthrough";
import { WALKTHROUGH } from "../src/lib/walkthrough-chapters";
import { isAlwaysPublicPath } from "../src/lib/public-paths";

const read = (path: string) => readFileSync(resolve(__dirname, "../..", path), "utf8");

const manifest: WalkthroughManifest = {
  url: "/media/walkthrough.mp4",
  poster: "/media/walkthrough-poster.jpg",
  captions: "/media/walkthrough.vtt",
  duration: 100,
  chapters: [
    { step: "intro", label: "Introduction", t: 0.2 },
    { step: "setup", label: "1 Set up", t: 20 },
    { step: "close", label: "What to do next", t: 90 },
  ],
};

test("times read as m:ss, rounded down, never negative", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(9.99), "0:09");
  assert.equal(formatTime(75.9), "1:15");
  assert.equal(formatTime(600), "10:00");
  assert.equal(formatTime(-3), "0:00");
  assert.equal(formatTime(Number.NaN), "0:00");
});

test("the current chapter is the last one that has started", () => {
  assert.equal(chapterFor(manifest.chapters, 0), 0);
  assert.equal(chapterFor(manifest.chapters, 19.9), 0);
  assert.equal(chapterFor(manifest.chapters, 20), 1);
  // A seek to 20 can read back as 19.999998.
  assert.equal(chapterFor(manifest.chapters, 19.999998), 1);
  assert.equal(chapterFor(manifest.chapters, 89), 1);
  assert.equal(chapterFor(manifest.chapters, 500), 2);
});

test("a chapter runs to the next one, and the last one to the end of the video", () => {
  assert.equal(chapterLength(manifest, "setup"), 70);
  assert.equal(chapterLength(manifest, "close"), 10);
  assert.equal(chapterLength(manifest, "missing"), null);
});

test("?video=<step> and #v=<step> open the guide at a step; unknown or empty steps open it at the start", () => {
  const { chapters } = manifest;
  assert.deepEqual(parseVideoParam("?video=setup", "", chapters), { step: "setup" });
  assert.deepEqual(parseVideoParam("", "#v=setup", chapters), { step: "setup" });
  assert.deepEqual(parseVideoParam("?video", "", chapters), { step: "intro" });
  assert.deepEqual(parseVideoParam("?video=1", "", chapters), { step: "intro" });
  assert.deepEqual(parseVideoParam("?video=retired-step", "", chapters), { step: "intro" });
  assert.deepEqual(parseVideoParam("?video=close", "#v=setup", chapters), { step: "close" });
  assert.equal(parseVideoParam("", "", chapters), null);
  assert.equal(parseVideoParam("?study=abc", "#survey", chapters), null);
  assert.equal(walkthroughHref(), "/walkthrough");
  assert.equal(walkthroughHref("research_brief"), "/walkthrough?video=research_brief");
});

test("the published chapter list is ordered, inside the video, and its media files are in public/", () => {
  const { chapters, duration } = WALKTHROUGH;
  assert.ok(chapters.length > 0);
  assert.equal(new Set(chapters.map((c) => c.step)).size, chapters.length);
  chapters.forEach((chapter, i) => {
    assert.ok(chapter.t >= 0 && chapter.t < duration, chapter.step);
    if (i > 0) assert.ok(chapter.t > chapters[i - 1].t, chapter.step);
  });
  for (const url of [WALKTHROUGH.url, WALKTHROUGH.poster, WALKTHROUGH.captions]) {
    assert.match(url, /^\/media\//);
    assert.ok(existsSync(resolve(__dirname, "../../public", url.slice(1))), `${url} is missing: run walkthrough/publish.sh`);
  }
  assert.match(read("public/media/walkthrough.vtt"), /^WEBVTT/);
});

test("every workflow step and standalone page links to its chapter of the video guide", () => {
  const sections: Record<string, string> = {
    "study-mode-section.tsx": "setup",
    "audience-section.tsx": "audience",
    "product-section.tsx": "product",
    "market-section.tsx": "market",
    "survey-section.tsx": "survey",
    "experiment-section.tsx": "experiment",
    "run-simulation-section.tsx": "run",
    "analysis-section.tsx": "result",
    "insights-section.tsx": "insights",
    "interview-synthesis-section.tsx": "interview",
    "research-brief-section.tsx": "research_brief",
    "interview-insights-section.tsx": "interview_insights",
  };
  for (const [file, step] of Object.entries(sections)) {
    assert.match(read(`src/components/sections/${file}`), new RegExp(`videoStep="${step}"`), file);
  }
  assert.match(read("src/app/interview/page.tsx"), /<WatchStepButton step="interview_page" \/>/);
  assert.match(read("src/app/focus-group/page.tsx"), /<WatchStepButton step="focus_group" \/>/);
});

test("the walkthrough page needs no sign-in, its look-alikes still do, and its media skip the middleware", () => {
  assert.equal(isAlwaysPublicPath("/walkthrough"), true);
  for (const path of ["/walkthroughs", "/walkthrough-admin", "/", "/interview", "/api/backend/api/v1/studies"]) {
    assert.equal(isAlwaysPublicPath(path), false, path);
  }
  const middleware = read("src/middleware.ts");
  assert.match(middleware, /import \{ isAlwaysPublicPath \} from "\.\/lib\/public-paths";/);
  // The matcher's negative lookahead: everything under /media/ bypasses the middleware, nothing else new does.
  assert.match(middleware, /"\/\(\(\?!_next\/static\|_next\/image\|favicon\.ico\|media\/\)\.\*\)"/);
  const matcher = /^\/(?!_next\/static|_next\/image|favicon\.ico|media\/).*$/;
  assert.equal(matcher.test(WALKTHROUGH.url), false);
  assert.equal(matcher.test("/mediakit"), true);
  assert.equal(matcher.test("/walkthrough"), true);
});

test("the guide is mounted on every page and reachable from the nav and both home pages", () => {
  assert.match(read("src/app/layout.tsx"), /<WalkthroughProvider>\{children\}<\/WalkthroughProvider>/);
  assert.match(read("src/components/ui/workflow-nav.tsx"), /walkthrough\.open\(\)/);
  assert.match(read("src/components/sections/main-hero-section.tsx"), /walkthrough\.open\(\)/);
  assert.match(read("src/components/ui/public-landing-shell.tsx"), /walkthroughHref\(\)/);
});
