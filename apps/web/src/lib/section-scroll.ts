import { workflowSections, type WorkflowSectionId } from "./workflow-sections";

/**
 * Window scroll position that brings a workflow section under the pinned top chrome
 * (the app-wide Demo (no AI) strip plus the sticky menu bar). `topChromeHeight` is the
 * total height of both in px, so the section's top edge lands right below them.
 * The first section scrolls to the very top, so the page opens exactly as it loads.
 */
export function sectionWindowScrollTop(
  id: WorkflowSectionId,
  elementDocumentTop: number,
  topChromeHeight: number,
  isDesktop: boolean,
): number {
  if (id === workflowSections[0].id) {
    return 0;
  }
  return Math.max(0, elementDocumentTop - topChromeHeight - (isDesktop ? 0 : 12));
}

/**
 * Converts a length read from a custom property on :root ("88px", "5.5rem", "40") to px.
 * Returns `fallback` for anything empty or unparseable, including unresolved expressions
 * such as "calc(...)".
 */
export function cssLengthToPx(rawValue: string, rootFontSizePx: number, fallback: number): number {
  const value = rawValue.trim();
  const parsed = Number.parseFloat(value);
  if (!value || !Number.isFinite(parsed)) {
    return fallback;
  }

  if (value.endsWith("rem")) {
    return Number.isFinite(rootFontSizePx) ? parsed * rootFontSizePx : fallback;
  }

  return parsed;
}

/**
 * The menu bar's own height in px, written to --nav-height on the workflow page.
 * Below lg the compact menu bar is as tall as its content (logo row, current step,
 * progress: about 210px on a phone or tablet), far more than the 132px/112px CSS
 * defaults, so whenever it is on screen (`compactMenuBarHeight` > 0) its measured height
 * is used. From lg up it is hidden (0) and the desktop bar, which is itself sized by
 * --nav-height, keeps the fixed 88px.
 */
export function menuBarHeightPx(viewportWidth: number, compactMenuBarHeight: number): number {
  if (Number.isFinite(compactMenuBarHeight) && compactMenuBarHeight > 0) {
    return compactMenuBarHeight;
  }

  if (viewportWidth >= 1024) {
    return 88;
  }

  return viewportWidth >= 640 ? 112 : 132;
}
