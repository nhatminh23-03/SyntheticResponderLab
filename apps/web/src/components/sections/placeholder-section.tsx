import { ReactNode } from "react";

import { GlassPanel } from "@/components/ui/glass-panel";
import { RevealOnScroll } from "@/components/ui/reveal-on-scroll";
import { SectionHeader } from "@/components/ui/section-header";
import { SectionWrapper } from "@/components/ui/section-wrapper";
import { WorkflowSectionId } from "@/lib/workflow-sections";

type PlaceholderSectionProps = {
  id: WorkflowSectionId;
  index: number;
  eyebrow: string;
  title: string;
  description: string;
  kicker: string;
  children?: ReactNode;
};

export function PlaceholderSection({
  id,
  index,
  eyebrow,
  title,
  description,
  kicker,
  children,
}: PlaceholderSectionProps) {
  return (
    <SectionWrapper id={id}>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(20rem,0.95fr)] lg:items-center">
        <RevealOnScroll>
          <SectionHeader
            index={index}
            eyebrow={eyebrow}
            title={title}
            description={description}
          />
        </RevealOnScroll>

        <RevealOnScroll delay={0.06}>
          <GlassPanel className="p-6 sm:p-8">
            <div className="rounded-[1.5rem] bg-[linear-gradient(180deg,rgba(17,24,29,0.74),rgba(17,24,29,0.38))] p-6 ring-1 ring-inset ring-white/5">
              <div className="text-[0.68rem] uppercase tracking-[0.24em] text-app-gold">
                {kicker}
              </div>
              <p className="mt-4 max-w-xl text-base leading-7 text-app-muted">
                This section is intentionally scaffolded and visually integrated
                into the one-page flow so the next implementation pass can plug
                directly into the same section shell, sticky nav, and
                scroll-registration system.
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
                  <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                    Frontend status
                  </div>
                  <div className="mt-2 text-base font-semibold text-app-text">
                    Section structure ready
                  </div>
                </div>
                <div className="rounded-2xl border border-white/6 bg-white/[0.03] p-4">
                  <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                    Backend fit
                  </div>
                  <div className="mt-2 text-base font-semibold text-app-text">
                    Thin-slice API available
                  </div>
                </div>
              </div>

              {children ? <div className="mt-8">{children}</div> : null}
            </div>
          </GlassPanel>
        </RevealOnScroll>
      </div>
    </SectionWrapper>
  );
}
