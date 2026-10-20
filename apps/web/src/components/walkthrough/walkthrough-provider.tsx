"use client";

import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { WalkthroughPlayer, type WalkthroughPlayerHandle } from "@/components/walkthrough/walkthrough-player";
import { WALKTHROUGH } from "@/lib/walkthrough-chapters";
import { formatTime, parseVideoParam, walkthroughHref } from "@/lib/walkthrough";

type WalkthroughContextValue = { open: (step?: string) => void };

// Outside the provider (it wraps every page from the root layout, so only in isolation) a request still
// reaches the video: on the public walkthrough page.
const WalkthroughContext = createContext<WalkthroughContextValue>({
  open: (step) => window.location.assign(walkthroughHref(step)),
});

export function useWalkthrough() {
  return useContext(WalkthroughContext);
}

/** Drops ?video= and #v= from the address once the guide closes, so a reload does not reopen it. */
function clearVideoParam() {
  const url = new URL(window.location.href);
  const hashHasVideo = new URLSearchParams(url.hash.slice(1)).has("v");
  if (!url.searchParams.has("video") && !hashHasVideo) return;
  url.searchParams.delete("video");
  if (hashHasVideo) url.hash = "";
  window.history.replaceState(window.history.state, "", url);
}

/** The "Video guide" dialog: one narrated video with chapters, opened from any page or by `?video=<step>`. */
export function WalkthroughProvider({ children }: { children: ReactNode }) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const playerRef = useRef<WalkthroughPlayerHandle | null>(null);
  const openedAt = useRef(0);
  const pressedOnBackdrop = useRef(false);
  const pathname = usePathname();
  const [activated, setActivated] = useState(false);

  const show = useCallback((step: string | null, play: boolean) => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) {
      dialog.showModal();
      openedAt.current = Date.now();
    }
    setActivated(true);
    // Still inside the click that asked for it, which Safari requires before it plays with sound.
    playerRef.current?.start(step, play);
    dialog.querySelector("video")?.focus();
  }, []);

  const open = useCallback((step?: string) => show(step ?? null, true), [show]);
  const value = useMemo(() => ({ open }), [open]);

  // A link such as /?video=survey opens the guide at that step. It does not start playing: browsers block
  // sound that no click asked for.
  useEffect(() => {
    if (window.location.pathname === "/walkthrough") return;
    const linked = parseVideoParam(window.location.search, window.location.hash, WALKTHROUGH.chapters);
    if (linked) show(linked.step, false);
  }, [show]);

  // Leaving the page (a link, or Back) closes the guide rather than leaving it playing over the next one.
  const shownPath = useRef(pathname);
  useEffect(() => {
    if (shownPath.current === pathname) return;
    shownPath.current = pathname;
    const dialog = dialogRef.current;
    if (dialog?.open) dialog.close();
  }, [pathname]);

  return (
    <WalkthroughContext.Provider value={value}>
      {children}
      <dialog
        ref={dialogRef}
        aria-labelledby="walkthrough-title"
        onClose={() => {
          playerRef.current?.pause();
          clearVideoParam();
        }}
        // A click outside the content closes the guide, but only when it also started outside: a drag that
        // ends on the backdrop, or the second click of a double-click on the button that opened it, does not.
        onPointerDown={(event) => {
          pressedOnBackdrop.current = event.target === event.currentTarget;
        }}
        onClick={(event) => {
          const onBackdrop = event.target === event.currentTarget && pressedOnBackdrop.current;
          if (onBackdrop && Date.now() - openedAt.current > 400) event.currentTarget.close();
        }}
        className="m-auto max-h-[calc(100dvh-1.5rem)] w-[min(76rem,calc(100vw-1.5rem))] max-w-none overflow-y-auto overscroll-contain rounded-2xl border p-0 text-app-text shadow-[0_24px_80px_rgba(0,0,0,0.45)] [background:var(--color-background)] [border-color:var(--button-secondary-border)] backdrop:bg-black/70 backdrop:backdrop-blur-sm"
      >
        <div className="p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <h2 id="walkthrough-title" className="font-display text-xl font-medium tracking-[-0.03em]">
                Video guide
              </h2>
              <p className="hidden text-sm text-app-muted sm:block">
                {formatTime(WALKTHROUGH.duration)} walkthrough, recorded in Demo (no AI) mode apart from one live run. Pick a chapter to jump to it.
              </p>
            </div>
            <form method="dialog" className="shrink-0">
              <button
                type="submit"
                aria-label="Close video guide"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border text-lg text-app-text transition hover:text-app-cyan [background:var(--button-secondary-bg)] [border-color:var(--button-secondary-border)]"
              >
                ×
              </button>
            </form>
          </div>
          <WalkthroughPlayer ref={playerRef} preload={activated ? "metadata" : "none"} idle={!activated} />
        </div>
      </dialog>
    </WalkthroughContext.Provider>
  );
}
