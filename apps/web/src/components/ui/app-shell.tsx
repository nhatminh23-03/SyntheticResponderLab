"use client";

import { PropsWithChildren } from "react";

import { ChapterNextArrow } from "@/components/ui/chapter-next-arrow";
import { WorkflowNav } from "@/components/ui/workflow-nav";

export function AppShell({ children }: PropsWithChildren) {
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
