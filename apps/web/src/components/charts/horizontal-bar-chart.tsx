import { motion } from "framer-motion";

import { ChartFrame } from "./chart-frame";
import { RankedBarDatum } from "./chart-types";
import { formatNumber } from "@/lib/chart-format";
import { normalizeRatio } from "@/lib/chart-scale";

type HorizontalBarChartProps = {
  title: string;
  subtitle?: string;
  rows: RankedBarDatum[];
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  headerless?: boolean;
  emptyMessage?: string;
  note?: string;
  highlightTopRow?: boolean;
};

export function HorizontalBarChart({
  title,
  subtitle,
  rows,
  badges,
  headerless = false,
  emptyMessage,
  note,
  highlightTopRow = false,
}: HorizontalBarChartProps) {
  const maxValue = rows.reduce((highest, row) => Math.max(highest, row.value), 0);
  const scaleTicks = buildScaleTicks(maxValue);

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      badges={badges}
      headerless={headerless}
      empty={rows.length === 0}
      emptyMessage={emptyMessage}
      note={note}
    >
      <div className="mb-5 flex items-center justify-between gap-3 text-[0.72rem] uppercase tracking-[0.2em] text-app-muted">
        <span>{highlightTopRow ? "Ranked comparison" : "Distribution"}</span>
        <span>{formatScaleValue(maxValue)}</span>
      </div>

      <div className="mb-4 grid grid-cols-5 gap-0 text-[0.68rem] text-app-muted">
        {scaleTicks.map((tick, index) => (
          <span
            key={`${title}-tick-${index}`}
            className={
              index === 0
                ? "text-left"
                : index === scaleTicks.length - 1
                ? "text-right"
                : "text-center"
            }
          >
            {tick}
          </span>
        ))}
      </div>

      <div className="space-y-4">
        {rows.map((row, index) => (
          <motion.div
            key={row.id}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.35, delay: index * 0.05 }}
            className="rounded-[1.05rem] border border-app-border [background:var(--hero-signal-card-bg)] p-4"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-app-border [background:var(--status-neutral-bg)] text-xs font-medium text-app-muted">
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-3 text-sm text-app-text">
                  <span className="truncate">{row.label}</span>
                  <span className="shrink-0 text-app-muted">
                    {row.valueLabel ?? formatNumber(row.value)}
                  </span>
                </div>
              </div>
            </div>

            {row.meta ? <div className="mt-1 text-xs leading-6 text-app-muted">{row.meta}</div> : null}

            <div className="mt-4 h-3 rounded-full border border-app-border [background:var(--status-neutral-bg)] p-[2px]">
                <motion.div
                  initial={{ scaleX: 0, opacity: 0.6 }}
                  whileInView={{ scaleX: 1, opacity: 1 }}
                  viewport={{ once: true, amount: 0.5 }}
                  transition={{ duration: 0.55, delay: 0.08 + index * 0.05, ease: "easeOut" }}
                  style={{
                    width: `${normalizeRatio(row.value, maxValue) * 100}%`,
                    transformOrigin: "left center",
                  }}
                  className={
                    highlightTopRow && index === 0
                      ? "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(216,186,103,0.92),rgba(15,216,255,0.84))] shadow-[0_0_20px_rgba(216,186,103,0.2)]"
                      : "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.82),rgba(216,186,103,0.76))]"
                  }
                >
                  <span className="absolute right-0 top-1/2 h-3 w-3 -translate-y-1/2 translate-x-1/2 rounded-full border border-white/20 bg-white/80 shadow-[0_0_18px_rgba(255,255,255,0.28)]" />
                </motion.div>
            </div>
          </motion.div>
        ))}
      </div>
    </ChartFrame>
  );
}

function buildScaleTicks(maxValue: number) {
  return [0, 0.25, 0.5, 0.75, 1].map((ratio) => formatScaleValue(maxValue * ratio));
}

function formatScaleValue(value: number) {
  if (value >= 10) {
    return formatNumber(value, 0);
  }
  if (value >= 1) {
    return formatNumber(value, 1);
  }
  return formatNumber(value, 2);
}
