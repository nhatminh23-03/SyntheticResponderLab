import { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function GlassPanel({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "glass-sheen relative overflow-hidden rounded-[2rem] border border-app-border bg-[linear-gradient(180deg,rgba(255,255,255,0.07)_0%,rgba(255,255,255,0.02)_16%,rgba(17,24,29,0.62)_100%)]",
        "shadow-card backdrop-blur-2xl",
        className
      )}
      {...props}
    />
  );
}
