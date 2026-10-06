"use client";

import { PropsWithChildren, useEffect, useLayoutEffect, useRef } from "react";

import { ChapterNextArrow } from "@/components/ui/chapter-next-arrow";
import { WorkflowNav } from "@/components/ui/workflow-nav";
import { menuBarHeightPx } from "@/lib/section-scroll";

const COMPACT_MENU_BAR_SELECTOR = "[data-compact-menu-bar]";

/**
 * Writes the menu bar's real height to --nav-height (and so to --top-chrome), measuring the
 * compact menu bar below lg, so section landings and anchor jumps clear the whole top chrome.
 */
function syncNavHeight(shell: HTMLElement | null) {
  if (!shell) {
    return; // unmounted: leave --nav-height to the CSS
  }
  const compactMenuBar = shell.querySelector<HTMLElement>(COMPACT_MENU_BAR_SELECTOR);
  document.documentElement.style.setProperty(
    "--nav-height",
    `${menuBarHeightPx(window.innerWidth, compactMenuBar?.offsetHeight ?? 0)}px`
  );
}

export function AppShell({ children }: PropsWithChildren) {
  const shellRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const shell = shellRef.current;
    const sync = () => syncNavHeight(shell);
    sync();

    // The compact bar changes height with its content and the viewport, and shows/hides at lg.
    const compactMenuBar = shell?.querySelector<HTMLElement>(COMPACT_MENU_BAR_SELECTOR);
    const observer =
      compactMenuBar && typeof ResizeObserver !== "undefined" ? new ResizeObserver(sync) : null;
    if (compactMenuBar && observer) {
      observer.observe(compactMenuBar);
    }
    window.addEventListener("resize", sync, { passive: true });

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", sync);
      // The signed-out landing page sizes its own menu bar by --nav-height: hand it back the CSS value.
      document.documentElement.style.removeProperty("--nav-height");
    };
  }, []);

  useLayoutEffect(() => {
    if (typeof window === "undefined" || window.location.hash) {
      return;
    }

    const previousScrollRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    window.scrollTo(0, 0);

    return () => {
      window.history.scrollRestoration = previousScrollRestoration;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || window.location.hash) {
      return;
    }

    let frameOne = 0;
    let frameTwo = 0;
    let timeoutId: number | null = null;

    const forceTop = () => {
      syncNavHeight(shellRef.current);
      window.scrollTo(0, 0);
    };

    forceTop();
    frameOne = window.requestAnimationFrame(() => {
      forceTop();
      frameTwo = window.requestAnimationFrame(() => {
        forceTop();
      });
    });
    timeoutId = window.setTimeout(() => {
      forceTop();
    }, 180);

    return () => {
      if (frameOne) {
        window.cancelAnimationFrame(frameOne);
      }
      if (frameTwo) {
        window.cancelAnimationFrame(frameTwo);
      }
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, []);

  return (
    <div ref={shellRef} className="relative min-h-screen overflow-x-clip bg-app-bg text-app-text">
      <div className="pointer-events-none fixed inset-0">
        <div
          className="absolute inset-x-0 top-0 h-[32rem]"
          style={{ background: "var(--app-backdrop-top)" }}
        />
        <div
          className="absolute right-[-9rem] top-[10rem] h-[24rem] w-[24rem] rounded-full blur-3xl"
          style={{ background: "var(--app-backdrop-gold)" }}
        />
        <div
          className="absolute left-[-12rem] top-[34rem] h-[26rem] w-[26rem] rounded-full blur-3xl"
          style={{ background: "var(--app-backdrop-cyan)" }}
        />
      </div>

      <WorkflowNav />

      <div className="relative">{children}</div>
      <ChapterNextArrow />
    </div>
  );
}
