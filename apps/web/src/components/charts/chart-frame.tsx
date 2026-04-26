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
          "rounded-[1.2rem] border border-app-border p-5 [background:var(--hero-signal-card-bg)]",
          className
        )}
      >
        {empty ? (
          <div className="rounded-[1rem] border border-dashed border-app-border px-4 py-5 text-sm leading-7 text-app-muted [background:var(--control-bg)]">
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
        "rounded-[1.25rem] border border-app-border p-3.5 [background:var(--hero-signal-card-bg)] [box-shadow:var(--hero-signal-card-shadow)] sm:p-4",
        className
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div>
          <div className="text-[0.72rem] uppercase tracking-[0.24em] text-app-muted">
            {title}
          </div>
          {subtitle ? <p className="mt-3 max-w-2xl text-sm leading-6 text-app-muted">{subtitle}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {badges?.map((badge) => (
            <BadgeChip key={`${title}-${badge.label}`} tone={badge.tone}>
              {badge.label}
            </BadgeChip>
          ))}
        </div>
      </div>

      <div className="relative mt-4 overflow-hidden rounded-[1rem] border border-app-border [background:var(--chart-shell-bg)]">
        <div className="pointer-events-none absolute inset-0 [background:var(--chart-shell-overlay)]" />
        <div
          className="pointer-events-none absolute inset-0 opacity-35"
          style={{
            backgroundImage: "var(--chart-shell-grid)",
            backgroundSize: "24% 100%, 100% 3rem",
          }}
        />
        <div className="relative p-3.5 sm:p-4">
        {empty ? (
            <div className="rounded-[1rem] border border-dashed border-app-border px-4 py-5 text-sm leading-7 text-app-muted [background:var(--control-bg)]">
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
