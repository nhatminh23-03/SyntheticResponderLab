import { motion } from "framer-motion";

import { ChartFrame } from "./chart-frame";
import { ModelDifferenceDatum } from "./chart-types";
import { formatNumber } from "@/lib/chart-format";
import { normalizeRatio } from "@/lib/chart-scale";

type ModelDifferenceChartProps = {
  title: string;
  subtitle?: string;
  rows: ModelDifferenceDatum[];
  models: string[];
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  emptyMessage?: string;
  note?: string;
};

export function ModelDifferenceChart({
  title,
  subtitle,
  rows,
  models,
  badges,
  emptyMessage,
  note,
}: ModelDifferenceChartProps) {
  const maxValue = rows.reduce(
    (highest, row) =>
      Math.max(highest, ...row.values.map((entry) => entry.value)),
    0
  );

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      badges={badges}
      empty={rows.length === 0 || models.length < 2}
      emptyMessage={emptyMessage}
      note={note}
    >
      <div className="mb-4 grid gap-2.5 text-xs text-app-muted sm:flex sm:flex-wrap sm:items-center sm:gap-x-5 sm:gap-y-3">
        {models.map((model, index) => (
          <div key={model} className="flex items-center gap-2">
            <span
              className={
                index === 0
                  ? "h-2.5 w-8 rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.84),rgba(15,216,255,0.58))]"
                  : "h-2.5 w-8 rounded-full bg-[linear-gradient(90deg,rgba(216,186,103,0.84),rgba(216,186,103,0.64))]"
              }
            />
            <span>{model}</span>
          </div>
        ))}
      </div>

      <div className="space-y-4">
        {rows.map((row, rowIndex) => (
          <motion.div
            key={row.id}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.35, delay: rowIndex * 0.05 }}
            className="rounded-[1.05rem] border border-app-border [background:var(--hero-signal-card-bg)] p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-app-text">{row.label}</div>
              <div className="text-xs uppercase tracking-[0.2em] text-app-muted">
                {row.spreadLabel ?? `spread ${formatNumber(row.spread)}`}
              </div>
            </div>
            <div className="mt-4 rounded-[1rem] border border-app-border [background:var(--status-neutral-bg)] p-3">
              <div className="mb-3 flex items-center justify-between gap-3 text-[0.62rem] uppercase tracking-[0.22em] text-app-muted">
                <span>Model spread</span>
                <span>{row.spreadLabel ?? `spread ${formatNumber(row.spread)}`}</span>
              </div>
              <div className="relative mb-5 h-10">
                <div className="absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-white/10" />
                {row.values.map((entry, index) => (
                  <motion.div
                    key={`${row.id}-${entry.model}-dot`}
                    initial={{ opacity: 0, scale: 0.6 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true, amount: 0.5 }}
                    transition={{ duration: 0.28, delay: 0.12 + rowIndex * 0.05 + index * 0.04 }}
                    className={
                      index === 0
                        ? "absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border border-white/20 bg-app-cyan shadow-[0_0_22px_rgba(15,216,255,0.34)]"
                        : "absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border border-white/20 bg-app-gold shadow-[0_0_22px_rgba(216,186,103,0.28)]"
                    }
                    style={{ left: `calc(${normalizeRatio(entry.value, maxValue) * 100}% - 0.5rem)` }}
                  />
                ))}
              </div>
              <div className="grid gap-3">
              {row.values.map((entry, index) => (
                <div key={`${row.id}-${entry.model}`} className="space-y-2">
                  <div className="flex items-center justify-between gap-3 text-sm text-app-text">
                    <span className="truncate">{entry.model}</span>
                    <span className="shrink-0 text-app-muted">
                      {entry.valueLabel ?? formatNumber(entry.value)}
                    </span>
                  </div>
                  <div className="h-3 rounded-full border border-app-border [background:var(--status-neutral-bg)] p-[2px]">
                    <motion.div
                      initial={{ scaleX: 0, opacity: 0.6 }}
                      whileInView={{ scaleX: 1, opacity: 1 }}
                      viewport={{ once: true, amount: 0.5 }}
                      transition={{ duration: 0.55, delay: 0.1 + rowIndex * 0.05 + index * 0.04, ease: "easeOut" }}
                      style={{ width: `${normalizeRatio(entry.value, maxValue) * 100}%`, transformOrigin: "left center" }}
                      className={
                        index === 0
                          ? "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.84),rgba(15,216,255,0.58))]"
                          : "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(216,186,103,0.84),rgba(216,186,103,0.64))]"
                      }
                    >
                      <span className="absolute right-0 top-1/2 h-3 w-3 -translate-y-1/2 translate-x-1/2 rounded-full border border-white/20 bg-white/80 shadow-[0_0_16px_rgba(255,255,255,0.24)]" />
                    </motion.div>
                  </div>
                </div>
              ))}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </ChartFrame>
  );
}
