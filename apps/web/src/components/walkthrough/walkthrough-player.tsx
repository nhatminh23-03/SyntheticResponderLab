"use client";

import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react";

import { WALKTHROUGH } from "@/lib/walkthrough-chapters";
import { chapterFor, chapterIndex, formatTime, type WalkthroughManifest } from "@/lib/walkthrough";
import { cn } from "@/lib/utils";

export type WalkthroughPlayerHandle = {
  /** Seek to a step's chapter (the start for null). Call it inside the click that asked for it when `play` is
   * true: Safari only lets a video start with sound from within a user gesture. */
  start: (step: string | null, play: boolean) => void;
  pause: () => void;
};

type WalkthroughPlayerProps = {
  manifest?: WalkthroughManifest;
  /** "none" while hidden in the closed guide, so nothing downloads until someone opens it. */
  preload?: "none" | "metadata";
  /** Until the guide is first opened, the poster and captions are left out too, so no page fetches them. */
  idle?: boolean;
  /** Height of everything above and below the video that has to stay on screen with it, so its controls are in
   * view without scrolling. */
  reserve?: string;
  /** A chapter the viewer picked from the list. */
  onChapter?: (step: string) => void;
  className?: string;
};

export const WalkthroughPlayer = forwardRef<WalkthroughPlayerHandle, WalkthroughPlayerProps>(
  function WalkthroughPlayer(
    { manifest = WALKTHROUGH, preload = "metadata", idle = false, reserve = "9rem", onChapter, className },
    ref
  ) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    // A seek asked for before the video knows its duration; applied once, when the metadata arrives.
    const pendingTime = useRef<number | null>(null);
    const [current, setCurrent] = useState(0);
    const [failed, setFailed] = useState(false);

    const seekTo = useCallback(
      (index: number, play: boolean) => {
        const video = videoRef.current;
        const chapter = manifest.chapters[index];
        if (!video || !chapter) return;
        setCurrent(index);
        if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
          video.currentTime = chapter.t;
        } else {
          pendingTime.current = chapter.t;
          // Shown without playing (a link to a step): fetch the metadata now, so the seek lands and the step's
          // frame is on screen, not the opening frame.
          if (!play && video.preload === "none") {
            video.preload = "metadata";
            video.load();
          }
        }
        // play() also starts loading; a browser may still refuse it, and the controls are there for that.
        if (play) void video.play().catch(() => undefined);
      },
      [manifest.chapters]
    );

    useImperativeHandle(
      ref,
      () => ({
        start: (step, play) => seekTo(chapterIndex(manifest.chapters, step) ?? 0, play),
        pause: () => videoRef.current?.pause(),
      }),
      [manifest.chapters, seekTo]
    );

    return (
      <div className={cn("grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_15rem]", className)}>
        <div className="min-w-0">
          {failed ? (
            <div
              role="alert"
              className="flex aspect-[16/10] items-center justify-center rounded-xl border p-6 text-center text-sm text-app-muted [border-color:var(--button-secondary-border)]"
            >
              The walkthrough video could not be loaded. Try again later, or open {manifest.url} directly.
            </div>
          ) : (
            <video
              ref={videoRef}
              // Never taller than the screen leaves room for, so the controls stay in view on short laptop
              // screens and landscape phones.
              className="mx-auto block aspect-[16/10] w-full rounded-xl bg-black"
              style={{ maxWidth: `calc((100dvh - ${reserve}) * 1.6)` }}
              src={manifest.url}
              poster={idle ? undefined : manifest.poster}
              controls
              playsInline
              preload={preload}
              onLoadedMetadata={(event) => {
                if (pendingTime.current === null) return;
                event.currentTarget.currentTime = pendingTime.current;
                pendingTime.current = null;
              }}
              onTimeUpdate={(event) => setCurrent(chapterFor(manifest.chapters, event.currentTarget.currentTime))}
              onError={() => setFailed(true)}
            >
              {idle ? null : <track kind="captions" src={manifest.captions} srcLang="en" label="English" default />}
            </video>
          )}
        </div>

        <nav aria-label="Video chapters" className="min-w-0">
          <ol className="fine-scrollbar grid gap-1 sm:grid-cols-2 lg:max-h-[min(60dvh,28rem)] lg:grid-cols-1 lg:overflow-y-auto lg:pr-1">
            {manifest.chapters.map((chapter, index) => (
              <li key={chapter.step}>
                <button
                  type="button"
                  onClick={() => {
                    seekTo(index, true);
                    onChapter?.(chapter.step);
                  }}
                  disabled={failed}
                  aria-current={index === current ? "step" : undefined}
                  className={cn(
                    "flex w-full items-baseline gap-3 rounded-lg border px-3 py-1.5 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-60",
                    index === current
                      ? "[background:var(--nav-active-pill-bg)] [border-color:var(--button-secondary-border)] text-app-text"
                      : "border-transparent text-app-muted hover:text-app-text hover:[background:var(--button-secondary-bg-hover)]"
                  )}
                >
                  <span className="w-10 shrink-0 tabular-nums text-app-cyan">{formatTime(chapter.t)}</span>
                  <span className="min-w-0">{chapter.label}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>
      </div>
    );
  }
);
