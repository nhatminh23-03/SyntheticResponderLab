import { motion } from "framer-motion";

import { ChartFrame } from "./chart-frame";
import { StepDatum } from "./chart-types";

type LadderChartProps = {
  title: string;
  subtitle?: string;
  steps: StepDatum[];
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  headerless?: boolean;
  emptyMessage?: string;
  note?: string;
};

export function LadderChart({
  title,
  subtitle,
  steps,
  badges,
  headerless = false,
  emptyMessage,
  note,
}: LadderChartProps) {
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      badges={badges}
      headerless={headerless}
      empty={steps.length === 0}
      emptyMessage={emptyMessage}
      note={note}
    >
      <div className="grid gap-4 xl:grid-cols-[repeat(4,minmax(0,1fr))]">
        {steps.map((step, index) => (
          <div key={step.id} className="relative">
            {index < steps.length - 1 ? (
              <motion.div
                initial={{ scaleX: 0, opacity: 0.3 }}
                whileInView={{ scaleX: 1, opacity: 1 }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{ duration: 0.45, delay: 0.12 + index * 0.08 }}
                className="pointer-events-none absolute left-[calc(100%-1rem)] right-[-1rem] top-[3.35rem] hidden h-px origin-left bg-[linear-gradient(90deg,rgba(15,216,255,0.48),rgba(216,186,103,0.42))] xl:block"
              />
            ) : null}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.35 }}
                transition={{ duration: 0.35, delay: index * 0.06 }}
              className="relative min-h-[13.5rem] rounded-[1.25rem] border border-app-border [background:var(--hero-signal-card-bg)] p-5"
            >
              <div className="text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
                Step {index + 1}
              </div>
              <div className="mt-3 text-base leading-7 text-app-text">{step.label}</div>
              <div className="mt-6 flex items-end justify-between gap-3">
                <div className="text-[2rem] font-medium leading-none text-app-cyan">
                  {step.valueLabel ?? `${step.value}`}
                </div>
                <div className="h-11 w-11 rounded-full border border-app-cyan/20 bg-app-cyan/10 shadow-[0_0_22px_rgba(15,216,255,0.1)]" />
              </div>
              <div className="mt-5 h-3 rounded-full border border-app-border [background:var(--status-neutral-bg)] p-[2px]">
                <motion.div
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: true, amount: 0.45 }}
                  transition={{ duration: 0.5, delay: 0.12 + index * 0.08, ease: "easeOut" }}
                  style={{ width: `${Math.max(0, Math.min(step.value, 100))}%`, transformOrigin: "left center" }}
                  className="h-full rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.84),rgba(216,186,103,0.76))]"
                />
              </div>
              {step.meta ? <div className="mt-3 text-xs leading-6 text-app-muted">{step.meta}</div> : null}
            </motion.div>
          </div>
        ))}
      </div>
    </ChartFrame>
  );
}
