import { ReactNode } from "react";

import { BadgeChip } from "@/components/ui/badge-chip";
import { cn } from "@/lib/utils";

import { ChartBadge } from "./chart-types";

type ChartFrameProps = {
  title: string;
  subtitle?: string;
  badges?: ChartBadge[];
  headerless?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  note?: string;
  className?: string;
  children?: ReactNode;
};

export function ChartFrame({
  title,
  subtitle,
  badges,
  headerless = false,
  empty = false,
  emptyMessage,
  note,
  className,
  children,
}: ChartFrameProps) {
  if (headerless) {
    return (
      <div
        className={cn(
          "rounded-[1.2rem] border border-white/6 bg-[linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.015))] p-5",
          className
        )}
      >
        {empty ? (
          <div className="rounded-[1rem] border border-dashed border-white/8 bg-white/[0.02] px-4 py-5 text-sm leading-7 text-app-muted">
            {emptyMessage ?? "No chart data is available yet."}
          </div>
        ) : (
          children
        )}
        {note ? <div className="mt-4 text-xs leading-6 text-app-muted">{note}</div> : null}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-[1.25rem] border border-white/6 bg-[linear-gradient(180deg,rgba(255,255,255,0.035),rgba(255,255,255,0.018))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]",
        className
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
            {title}
          </div>
          {subtitle ? <p className="mt-3 max-w-2xl text-sm leading-6 text-app-muted">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {badges?.map((badge) => (
            <BadgeChip key={`${title}-${badge.label}`} tone={badge.tone}>
              {badge.label}
            </BadgeChip>
          ))}
        </div>
      </div>

      <div className="relative mt-4 overflow-hidden rounded-[1rem] border border-white/6 bg-[linear-gradient(180deg,rgba(8,12,16,0.5),rgba(8,12,16,0.26))]">
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(15,216,255,0.03),transparent_28%,transparent_72%,rgba(216,186,103,0.03))]" />
        <div className="pointer-events-none absolute inset-0 opacity-35 [background-image:linear-gradient(to_right,rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.035)_1px,transparent_1px)] [background-size:24%_100%,100%_3rem]" />
        <div className="relative p-4">
        {empty ? (
            <div className="rounded-[1rem] border border-dashed border-white/8 bg-white/[0.02] px-4 py-5 text-sm leading-7 text-app-muted">
            {emptyMessage ?? "No chart data is available yet."}
          </div>
        ) : (
          children
        )}
        </div>
      </div>

      {note ? <div className="mt-4 text-xs leading-6 text-app-muted">{note}</div> : null}
    </div>
  );
}
