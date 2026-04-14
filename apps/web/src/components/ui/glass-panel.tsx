import { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function GlassPanel({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "glass-sheen relative overflow-hidden rounded-[2rem] border border-app-border [background:var(--glass-panel-bg)]",
        "shadow-[var(--glass-panel-shadow)] backdrop-blur-2xl",
        className
      )}
      {...props}
    />
  );
}
