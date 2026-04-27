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
        "relative scroll-mt-[calc(var(--nav-height)+1rem)] px-4 sm:px-5 md:px-8 lg:scroll-mt-[calc(var(--nav-height)+0.75rem)] lg:px-12 xl:px-16",
        fullHeight && "lg:h-[calc(100svh-var(--nav-height))]",
        className
      )}
    >
      {scrollable ? (
        <div
          ref={scrollContainerRef}
          className={cn(
            "fine-scrollbar mx-auto w-full max-w-[88rem] overflow-visible py-6 sm:py-8 lg:h-full lg:overflow-y-auto lg:overscroll-contain lg:py-7 lg:pr-1",
            contentClassName
          )}
        >
          {children}
        </div>
      ) : (
        <div
          className={cn(
            "mx-auto flex w-full max-w-[88rem] flex-col py-6 sm:py-8 lg:h-full lg:justify-center lg:py-7",
            contentClassName
          )}
        >
          {children}
        </div>
      )}
    </section>
  );
}
