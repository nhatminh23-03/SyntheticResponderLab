import { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

type BadgeChipProps = PropsWithChildren<{
  tone?: "cyan" | "gold" | "neutral";
  className?: string;
}>;

export function BadgeChip({
  children,
  tone = "neutral",
  className,
}: BadgeChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.24em]",
        tone === "cyan" &&
          "[background:var(--chip-cyan-bg)] [color:var(--chip-cyan-text)] [box-shadow:var(--chip-cyan-shadow)]",
        tone === "gold" &&
          "[background:var(--chip-gold-bg)] [color:var(--chip-gold-text)] [box-shadow:var(--chip-gold-shadow)]",
        tone === "neutral" &&
          "[color:var(--status-neutral-text)] [background:var(--badge-neutral-bg)] [box-shadow:inset_0_0_0_1px_var(--badge-neutral-border)]",
        className
      )}
    >
      {children}
    </span>
  );
}
