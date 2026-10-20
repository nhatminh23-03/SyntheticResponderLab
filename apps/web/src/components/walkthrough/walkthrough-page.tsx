"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef } from "react";

import { WalkthroughPlayer, type WalkthroughPlayerHandle } from "@/components/walkthrough/walkthrough-player";
import { AppLogoMark } from "@/components/ui/workflow-nav";
import { WALKTHROUGH } from "@/lib/walkthrough-chapters";
import { formatTime, parseVideoParam, walkthroughHref } from "@/lib/walkthrough";

/** The public walkthrough: the same video and chapters as the in-app guide, for anyone with the link. */
export function WalkthroughPage() {
  const player = useRef<WalkthroughPlayerHandle | null>(null);

  // /walkthrough?video=survey (or #v=survey) starts at that chapter. When only the #v= part changes, the hash
  // wins over a ?video= left in the address by an earlier pick.
  const followLink = useCallback((hashOnly: boolean) => {
    const search = hashOnly ? "" : window.location.search;
    const linked = parseVideoParam(search, window.location.hash, WALKTHROUGH.chapters);
    if (linked) player.current?.start(linked.step, false);
  }, []);

  useEffect(() => {
    const onHash = () => followLink(true);
    const onHistory = () => followLink(false);
    followLink(false);
    window.addEventListener("hashchange", onHash);
    window.addEventListener("popstate", onHistory);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("popstate", onHistory);
    };
  }, [followLink]);

  // The address follows the chapter picked, so a copied link opens the same step.
  const rememberChapter = useCallback((step: string) => {
    window.history.replaceState(window.history.state, "", walkthroughHref(step));
  }, []);

  return (
    <div className="min-h-screen bg-app-bg text-app-text">
      <header className="border-b [background:var(--nav-bg)] [border-color:var(--nav-border)]">
        <div className="mx-auto flex w-full max-w-[76rem] items-center justify-between gap-4 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <AppLogoMark className="h-9 w-9" />
            <div className="truncate font-display text-[0.86rem] font-semibold uppercase tracking-[0.08em] text-app-cyan">
              Grounded Synthetic Respondent Lab
            </div>
          </div>
          <Link
            href="/"
            className="inline-flex h-9 shrink-0 items-center rounded-full border px-4 text-[0.82rem] font-medium transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
          >
            Open the app
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[76rem] px-4 pb-10 pt-4 sm:px-6">
        <h1 className="font-display text-[1.6rem] font-medium leading-tight tracking-[-0.03em] sm:text-[1.9rem]">
          Video walkthrough
        </h1>
        <p className="mt-0.5 text-sm text-app-muted">
          {formatTime(WALKTHROUGH.duration)} · narrated · captions on · pick a chapter to jump to it
        </p>
        {/* Everything above the video, plus a margin below it, so the controls are on screen without scrolling. */}
        <WalkthroughPlayer ref={player} reserve="14rem" onChapter={rememberChapter} className="mt-3" />
        <p className="mt-5 max-w-3xl text-[0.95rem] leading-7 text-app-muted">
          A tour of the app: setting up and running a survey study, reading the results, and the interview and
          focus-group tools. Apart from one live run with Jev, it was recorded in Demo (no AI) mode, so the answers
          shown are saved synthetic answers.
        </p>
      </main>
    </div>
  );
}
