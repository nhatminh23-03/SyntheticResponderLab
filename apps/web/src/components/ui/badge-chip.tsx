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
          "bg-[rgba(15,216,255,0.12)] text-app-cyan shadow-[0_0_18px_rgba(15,216,255,0.16)]",
        tone === "gold" &&
          "bg-[rgba(216,186,103,0.12)] text-app-gold shadow-[0_0_18px_rgba(216,186,103,0.14)]",
        tone === "neutral" &&
          "bg-white/5 text-app-muted ring-1 ring-inset ring-white/10",
        className
      )}
    >
      {children}
    </span>
  );
}
