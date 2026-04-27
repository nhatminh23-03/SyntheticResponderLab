import { motion } from "framer-motion";

import { ChartFrame } from "./chart-frame";
import { GroupedBarDatum } from "./chart-types";
import { formatNumber } from "@/lib/chart-format";
import { normalizeRatio } from "@/lib/chart-scale";

type GroupedBarChartProps = {
  title: string;
  subtitle?: string;
  rows: GroupedBarDatum[];
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  headerless?: boolean;
  emptyMessage?: string;
  note?: string;
};

export function GroupedBarChart({
  title,
  subtitle,
  rows,
  badges,
  headerless = false,
  emptyMessage,
  note,
}: GroupedBarChartProps) {
  const maxValue = rows.reduce(
    (highest, row) =>
      Math.max(
        highest,
        ...row.series.map((seriesRow) =>
          typeof seriesRow.value === "number" ? seriesRow.value : 0
        )
      ),
    0
  );

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
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="grid gap-2 text-xs text-app-muted sm:flex sm:flex-wrap sm:items-center sm:gap-x-5 sm:gap-y-3">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-8 rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.82),rgba(15,216,255,0.56))]" />
            <span>Appeal</span>
          </div>
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-8 rounded-full bg-[linear-gradient(90deg,rgba(216,186,103,0.84),rgba(216,186,103,0.64))]" />
            <span>Purchase likelihood</span>
          </div>
        </div>
        <div className="text-[0.72rem] uppercase tracking-[0.2em] text-app-muted">
          scale 0 to {formatNumber(maxValue, maxValue >= 10 ? 0 : 1)}
        </div>
      </div>

      <div className="mb-4 hidden grid-cols-5 gap-0 text-[0.68rem] text-app-muted sm:grid">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio, index) => (
          <span
            key={`${title}-tick-${index}`}
            className={
              index === 0
                ? "text-left"
                : index === 4
                ? "text-right"
                : "text-center"
            }
          >
            {formatNumber(maxValue * ratio, maxValue >= 10 ? 0 : 1)}
          </span>
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
            className="rounded-[1.05rem] border border-app-border [background:var(--hero-signal-card-bg)] p-3.5 sm:p-4"
          >
            <div className="mb-4 text-sm font-medium text-app-text">{row.label}</div>
            <div className="space-y-3">
              {row.series.map((seriesRow, index) => (
                <div key={`${row.id}-${seriesRow.key}`} className="space-y-2">
                  <div className="flex items-start justify-between gap-3 text-sm text-app-text">
                    <span className="min-w-0 leading-6 sm:truncate">{seriesRow.label}</span>
                    <span className="shrink-0 text-app-muted">
                      {seriesRow.valueLabel ??
                        (typeof seriesRow.value === "number"
                          ? formatNumber(seriesRow.value)
                          : "n/a")}
                    </span>
                  </div>
                  <div className="h-3 rounded-full border border-app-border [background:var(--status-neutral-bg)] p-[2px]">
                      <motion.div
                        initial={{ scaleX: 0, opacity: 0.6 }}
                        whileInView={{ scaleX: 1, opacity: 1 }}
                        viewport={{ once: true, amount: 0.5 }}
                        transition={{
                          duration: 0.55,
                          delay: 0.08 + rowIndex * 0.05 + index * 0.04,
                          ease: "easeOut",
                        }}
                        style={{
                          width: `${normalizeRatio(seriesRow.value ?? 0, maxValue) * 100}%`,
                          transformOrigin: "left center",
                        }}
                        className={
                          seriesRow.tone === "gold"
                            ? "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(216,186,103,0.88),rgba(216,186,103,0.68))]"
                            : "relative h-full rounded-full bg-[linear-gradient(90deg,rgba(15,216,255,0.84),rgba(15,216,255,0.58))]"
                        }
                        >
                          <span className="absolute right-0 top-1/2 h-3 w-3 -translate-y-1/2 translate-x-1/2 rounded-full border border-white/20 bg-white/80 shadow-[0_0_16px_rgba(255,255,255,0.24)]" />
                        </motion.div>
                  </div>
                  <div className="flex items-center justify-between text-[0.68rem] text-app-muted sm:hidden">
                    <span>0</span>
                    <span>{formatNumber(maxValue, maxValue >= 10 ? 0 : 1)}</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        ))}
      </div>
    </ChartFrame>
  );
}
