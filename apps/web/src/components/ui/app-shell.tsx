"use client";

import { PropsWithChildren } from "react";

import { ChapterNextArrow } from "@/components/ui/chapter-next-arrow";
import { WorkflowNav } from "@/components/ui/workflow-nav";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="relative min-h-screen overflow-x-clip bg-app-bg text-app-text">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-x-0 top-0 h-[32rem] bg-[radial-gradient(circle_at_top,rgba(15,216,255,0.16),transparent_55%)]" />
        <div className="absolute right-[-9rem] top-[10rem] h-[24rem] w-[24rem] rounded-full bg-[radial-gradient(circle,rgba(216,186,103,0.12),transparent_65%)] blur-3xl" />
        <div className="absolute left-[-12rem] top-[34rem] h-[26rem] w-[26rem] rounded-full bg-[radial-gradient(circle,rgba(15,216,255,0.1),transparent_65%)] blur-3xl" />
      </div>

      <WorkflowNav />

      <div className="relative">{children}</div>
      <ChapterNextArrow />
    </div>
  );
}
