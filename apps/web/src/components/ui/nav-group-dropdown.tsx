"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { NavGroup, WorkflowSectionId } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";

type Props = {
  group: NavGroup;
  isAnyChildActive: boolean;
  navigationLocked: boolean;
  activeSectionId: string | null;
  onItemSelect: (id: WorkflowSectionId) => void;
};

export function NavGroupDropdown({
  group,
  isAnyChildActive,
  navigationLocked,
  activeSectionId,
  onItemSelect,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, []);

  const isGold = group.variant === "gold";

  return (
    <div ref={containerRef} className="relative shrink-0">
      {/* Trigger */}
      <button
        type="button"
        disabled={navigationLocked}
        onClick={() => setIsOpen((v) => !v)}
        className={cn(
          "relative inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-2 text-sm tracking-[0.01em] transition-colors",
          navigationLocked && "cursor-not-allowed opacity-55",
          isGold
            ? "border border-app-gold/30 bg-[rgba(216,186,103,0.14)] text-app-gold"
            : isAnyChildActive
            ? "text-app-text"
            : "text-app-muted hover:text-app-cyan"
        )}
      >
        {group.label}
        {/* Chevron */}
        <motion.svg
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.18 }}
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className="shrink-0"
          aria-hidden
        >
          <path
            d="M2 4l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.svg>

        {/* Active underline indicator — shares layoutId with flat nav indicator */}
        {isAnyChildActive && !isGold ? (
          <motion.span
            layoutId="workflow-nav-indicator"
            className="absolute inset-x-3 bottom-0 h-px bg-app-cyan shadow-[0_0_18px_rgba(15,216,255,0.42)]"
          />
        ) : null}
      </button>

      {/* Dropdown panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 top-[calc(100%+0.5rem)] z-50 min-w-[11rem] rounded-2xl border border-white/[0.08] bg-[rgba(10,15,19,0.92)] p-1.5 shadow-[0_8px_40px_rgba(0,0,0,0.5),0_0_0_1px_rgba(118,228,255,0.06)] backdrop-blur-2xl"
          >
            {group.items.map((item) => {
              const isActive = item.id === activeSectionId;
              const isComingSoon = item.kind === "coming-soon";

              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={isComingSoon}
                  onClick={() => {
                    if (item.kind === "section") {
                      onItemSelect(item.id);
                      setIsOpen(false);
                    }
                  }}
                  className={cn(
                    "flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors",
                    isComingSoon
                      ? "cursor-not-allowed text-app-muted opacity-50"
                      : isActive
                      ? "bg-white/[0.06] text-app-text"
                      : "text-app-muted hover:bg-white/[0.04] hover:text-app-cyan"
                  )}
                >
                  <span>{item.label}</span>
                  {isComingSoon && (
                    <span className="ml-2 shrink-0 rounded-full border border-white/[0.10] px-1.5 py-0.5 text-[0.6rem] uppercase tracking-[0.12em] text-app-muted">
                      Soon
                    </span>
                  )}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
