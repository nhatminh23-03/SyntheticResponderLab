"use client";

import { PropsWithChildren, useEffect, useRef } from "react";

import { useSectionRegistry } from "@/providers/section-registry-provider";
import { WorkflowSectionId } from "@/lib/workflow-sections";
import { cn } from "@/lib/utils";

type SectionWrapperProps = PropsWithChildren<{
  id: WorkflowSectionId;
  className?: string;
  contentClassName?: string;
  fullHeight?: boolean;
  scrollable?: boolean;
}>;

export function SectionWrapper({
  id,
  className,
  contentClassName,
  fullHeight = true,
  scrollable = false,
  children,
}: SectionWrapperProps) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const { registerScrollContainer, registerSection } = useSectionRegistry();

  useEffect(() => {
    registerSection(id, sectionRef.current);
    registerScrollContainer(id, scrollable ? scrollContainerRef.current : null);

    return () => {
      registerSection(id, null);
      registerScrollContainer(id, null);
    };
  }, [id, registerScrollContainer, registerSection, scrollable]);

  return (
    <section
      id={id}
      ref={sectionRef}
      data-section-id={id}
      className={cn(
        "relative scroll-mt-[calc(var(--nav-height)+1.25rem)] px-6 md:px-10 lg:px-16",
        fullHeight && "h-[calc(100svh-var(--nav-height))]",
        className
      )}
    >
      {scrollable ? (
        <div
          ref={scrollContainerRef}
          className={cn(
            "fine-scrollbar mx-auto h-full w-full max-w-[88rem] overflow-y-auto overscroll-contain py-6 pr-1 md:py-7",
            contentClassName
          )}
        >
          {children}
        </div>
      ) : (
        <div
          className={cn(
            "mx-auto flex h-full w-full max-w-[88rem] flex-col justify-center py-6 md:py-7",
            contentClassName
          )}
        >
          {children}
        </div>
      )}
    </section>
  );
}
