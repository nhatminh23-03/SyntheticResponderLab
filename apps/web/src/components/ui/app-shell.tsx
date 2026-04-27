"use client";

import { PropsWithChildren, useEffect, useLayoutEffect } from "react";

import { ChapterNextArrow } from "@/components/ui/chapter-next-arrow";
import { WorkflowNav } from "@/components/ui/workflow-nav";

function resolveNavHeightPx(width: number) {
  if (width >= 1024) {
    return 88;
  }

  if (width >= 640) {
    return 112;
  }

  return 132;
}

export function AppShell({ children }: PropsWithChildren) {
  useLayoutEffect(() => {
    if (typeof window === "undefined" || window.location.hash) {
      return;
    }

    const applyNavHeight = () => {
      document.documentElement.style.setProperty(
        "--nav-height",
        `${resolveNavHeightPx(window.innerWidth)}px`
      );
    };

    const previousScrollRestoration = window.history.scrollRestoration;
    applyNavHeight();
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
      document.documentElement.style.setProperty(
        "--nav-height",
        `${resolveNavHeightPx(window.innerWidth)}px`
      );
      window.scrollTo(0, 0);
    };

    const handleResize = () => {
      document.documentElement.style.setProperty(
        "--nav-height",
        `${resolveNavHeightPx(window.innerWidth)}px`
      );
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

    window.addEventListener("resize", handleResize, { passive: true });

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
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return (
    <div className="relative min-h-screen overflow-x-clip bg-app-bg text-app-text">
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
