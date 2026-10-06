import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cssLengthToPx, menuBarHeightPx, sectionWindowScrollTop } from "../src/lib/section-scroll";
import { workflowSections } from "../src/lib/workflow-sections";

const read = (path: string) => readFileSync(resolve(__dirname, "../..", path), "utf8");

test("going back to the first section scrolls to the very top, so the app-wide Demo switch above it is visible again", () => {
  // Desktop: the first section starts right under the 41px Demo strip; landing on its top edge (42) hid the strip for good.
  assert.equal(sectionWindowScrollTop(workflowSections[0].id, 42, 0, true), 0);
  assert.equal(sectionWindowScrollTop(workflowSections[0].id, 120, 64, false), 0);
  // With the strip pinned, the first section sits under the whole top chrome (40px strip + 88px menu bar).
  assert.equal(sectionWindowScrollTop(workflowSections[0].id, 128, 128, true), 0);
});

test("other sections keep their offset under the sticky nav", () => {
  assert.equal(sectionWindowScrollTop("survey", 4300, 89, true), 4211);
  assert.equal(sectionWindowScrollTop("survey", 4300, 64, false), 4224);
});

test("other sections land right under the pinned Demo strip plus the menu bar, not under the menu bar alone", () => {
  // Desktop: 40px strip + 88px menu bar. Offsetting by the menu bar alone would leave 40px of the section under the strip.
  assert.equal(sectionWindowScrollTop("survey", 4300, 40 + 88, true), 4172);
  // Mobile keeps its extra 12px breathing room below the chrome (40px strip + 132px menu bar).
  assert.equal(sectionWindowScrollTop("survey", 4300, 40 + 132, false), 4116);
});

test("a section near the top never yields a negative scroll position", () => {
  assert.equal(sectionWindowScrollTop("study-mode", 30, 89, true), 0);
});

test("top-chrome lengths read from CSS variables convert to px", () => {
  assert.equal(cssLengthToPx("88px", 16, 0), 88);
  assert.equal(cssLengthToPx(" 2.5rem ", 16, 0), 40);
  assert.equal(cssLengthToPx("5.5rem", 20, 0), 110);
  assert.equal(cssLengthToPx("40", 16, 0), 40);
  // Unset or unresolvable values fall back instead of producing NaN scroll targets.
  assert.equal(cssLengthToPx("", 16, 40), 40);
  assert.equal(cssLengthToPx("calc(88px + 2.5rem)", 16, 128), 128);
  assert.equal(cssLengthToPx("2.5rem", Number.NaN, 40), 40);
});

test("the Demo strip, the menu bars and the viewport-height panels share one top-chrome contract", () => {
  const css = read("src/app/globals.css");
  assert.match(css, /--demo-bar-height:\s*2\.5rem;/);
  assert.match(css, /--top-chrome:\s*calc\(var\(--nav-height\) \+ var\(--demo-bar-height\)\);/);

  // The strip is pinned at the very top, above the z-50 menu bars, at exactly the variable's height.
  const strip = read("src/components/demo/demo-mode.tsx");
  assert.match(strip, /className="sticky top-0 z-\[60\] flex h-\[var\(--demo-bar-height\)\] items-center/);

  // Every sticky menu bar sticks right below the strip instead of sliding behind it.
  for (const file of ["src/components/ui/workflow-nav.tsx", "src/components/ui/public-landing-shell.tsx"]) {
    const headers = read(file).match(/<header\b[^>]*>/g) ?? [];
    assert.ok(headers.length > 0, file);
    for (const header of headers) {
      assert.match(header, /className="sticky top-\[var\(--demo-bar-height\)\] z-50 /, `${file}: ${header}`);
    }
  }

  // Desktop panels fit the viewport below both, and anchor jumps clear both.
  const wrapper = read("src/components/ui/section-wrapper.tsx");
  assert.match(wrapper, /lg:h-\[calc\(100svh-var\(--top-chrome\)\)\]/);
  assert.doesNotMatch(wrapper, /var\(--nav-height\)/);

  // Programmatic section scrolling and active-section detection use the strip too.
  const provider = read("src/providers/section-registry-provider.tsx");
  assert.match(provider, /getPropertyValue\("--demo-bar-height"\)/);
  assert.doesNotMatch(provider, /resolveNavHeight\(\)/);
});

test("below lg the menu bar height is the compact bar's measured height, not the much shorter CSS default", () => {
  // Phone and tablet: the compact bar (logo row, current step, progress) is about 210px; the defaults said 132/112.
  assert.equal(menuBarHeightPx(375, 210), 210);
  assert.equal(menuBarHeightPx(768, 211), 211);
  // So a phone section landing clears the 40px strip plus the real bar: 4300 - (40 + 210) - 12.
  assert.equal(sectionWindowScrollTop("survey", 4300, 40 + menuBarHeightPx(375, 210), false), 4038);
  // Desktop: the compact bar is hidden (0) and the desktop bar is sized by --nav-height itself, so it stays 88.
  assert.equal(menuBarHeightPx(1440, 0), 88);
  assert.equal(menuBarHeightPx(1024, 0), 88);
  // Not measured yet (or missing): the old per-breakpoint values.
  assert.equal(menuBarHeightPx(768, 0), 112);
  assert.equal(menuBarHeightPx(375, 0), 132);
  assert.equal(menuBarHeightPx(375, Number.NaN), 132);
});

test("the workflow page keeps --nav-height equal to the compact menu bar it renders", () => {
  const nav = read("src/components/ui/workflow-nav.tsx");
  // Exactly one header is the compact (lg:hidden) bar, and it carries the measuring hook.
  const compact = (nav.match(/<header\b[^>]*>/g) ?? []).filter((header) => header.includes("data-compact-menu-bar"));
  assert.equal(compact.length, 1);
  assert.match(compact[0], /lg:hidden/);
  assert.doesNotMatch(compact[0], /var\(--nav-height\)/);

  const shell = read("src/components/ui/app-shell.tsx");
  assert.match(shell, /querySelector<HTMLElement>\(COMPACT_MENU_BAR_SELECTOR\)/);
  assert.match(shell, /const COMPACT_MENU_BAR_SELECTOR = "\[data-compact-menu-bar\]";/);
  assert.match(shell, /new ResizeObserver\(sync\)/);
  assert.match(shell, /menuBarHeightPx\(window\.innerWidth, compactMenuBar\?\.offsetHeight \?\? 0\)/);
  // The signed-out landing page sizes its own bar by --nav-height, so the measured value must not outlive the shell.
  assert.match(shell, /removeProperty\("--nav-height"\)/);
});
