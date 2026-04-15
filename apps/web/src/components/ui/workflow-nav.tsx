"use client";

import { useMemo } from "react";

import { navGroups } from "@/lib/workflow-sections";
import { useSectionRegistry } from "@/providers/section-registry-provider";
import { NavGroupDropdown } from "@/components/ui/nav-group-dropdown";

export function WorkflowNav() {
  const { activeSectionId, navigationLocked, scrollToSection } = useSectionRegistry();

  const activeGroupIds = useMemo(() => {
    const set = new Set<string>();
    for (const group of navGroups) {
      if (group.items.some((item) => item.id === activeSectionId)) {
        set.add(group.id);
      }
    }
    return set;
  }, [activeSectionId]);

  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-[rgba(10,15,19,0.78)] backdrop-blur-2xl">
      <div className="mx-auto flex h-[var(--nav-height)] w-full max-w-[92rem] items-center gap-4 px-4 md:px-6 lg:px-10">
        <button
          type="button"
          onClick={() => scrollToSection("main")}
          className="flex min-w-0 shrink-0 items-center gap-3 text-left"
        >
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-[rgba(216,186,103,0.12)] font-display text-sm font-extrabold tracking-[0.18em] text-app-gold">
            GL
          </span>
          <div className="min-w-0 max-w-[13rem] md:max-w-[16rem] xl:max-w-[20rem]">
            <div className="truncate font-display text-xs font-semibold uppercase tracking-[0.18em] text-app-cyan md:text-sm">
              Grounded Synthetic Respondent Lab
            </div>
            <div className="hidden text-[0.68rem] tracking-[0.16em] text-app-muted lg:block">
              Premium grounded research workflow
            </div>
          </div>
        </button>

        <nav className="flex min-w-0 flex-1 items-center gap-1">
          {navGroups.map((group) => (
            <NavGroupDropdown
              key={group.id}
              group={group}
              isAnyChildActive={activeGroupIds.has(group.id)}
              navigationLocked={navigationLocked}
              activeSectionId={activeSectionId}
              onItemSelect={scrollToSection}
            />
          ))}
        </nav>
      </div>
    </header>
  );
}
