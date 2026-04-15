import { motion } from "framer-motion";

import { ChartFrame } from "./chart-frame";
import { HeatmapColumn, HeatmapDatum } from "./chart-types";
import { formatNumber } from "@/lib/chart-format";
import { heatmapOpacity, numericExtent } from "@/lib/chart-scale";

type HeatmapGridProps = {
  title: string;
  subtitle?: string;
  columns: HeatmapColumn[];
  rows: HeatmapDatum[];
  badges?: Array<{ label: string; tone?: "cyan" | "gold" | "neutral" }>;
  emptyMessage?: string;
  note?: string;
};

export function HeatmapGrid({
  title,
  subtitle,
  columns,
  rows,
  badges,
  emptyMessage,
  note,
}: HeatmapGridProps) {
  const { min, max } = numericExtent(
    rows.flatMap((row) => row.values.map((entry) => entry.value))
  );

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      badges={badges}
      empty={rows.length === 0 || columns.length === 0}
      emptyMessage={emptyMessage}
      note={note}
    >
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 text-xs text-app-muted">
        <span>Lower signal</span>
        <div className="flex w-52 overflow-hidden rounded-full border border-app-border shadow-[0_0_18px_rgba(15,216,255,0.08)]">
          <div className="h-2.5 flex-1 bg-[rgba(15,216,255,0.14)]" />
          <div className="h-2.5 flex-1 bg-[rgba(15,216,255,0.28)]" />
          <div className="h-2.5 flex-1 bg-[rgba(15,216,255,0.42)]" />
          <div className="h-2.5 flex-1 bg-[linear-gradient(90deg,rgba(15,216,255,0.56),rgba(216,186,103,0.46))]" />
        </div>
        <span>Higher signal</span>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[58rem] overflow-hidden rounded-[1.2rem] border border-app-border [background:var(--hero-signal-card-bg)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
          <table className="min-w-full divide-y divide-white/6 text-sm">
            <thead className="[background:var(--status-neutral-bg)] text-app-muted">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Question</th>
                {columns.map((column) => (
                  <th key={column.key} className="px-4 py-3 text-left font-medium">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={row.id} className="border-t border-app-border">
                  <td className={rowIndex % 2 === 0 ? "[background:var(--button-secondary-bg)] px-5 py-4 text-app-text" : "px-5 py-4 text-app-text"}>
                    <div className="max-w-[24rem] leading-7">{row.label}</div>
                  </td>
                  {row.values.map((entry) => {
                    const opacity = heatmapOpacity(entry.value, min, max);
                    const baseOpacity = 0.12 + opacity * 0.38;
                    return (
                      <td key={`${row.id}-${entry.key}`} className={rowIndex % 2 === 0 ? "[background:var(--button-secondary-bg)] px-5 py-4" : "px-5 py-4"}>
                        <motion.div
                          initial={{ opacity: 0, scale: 0.96 }}
                          whileInView={{ opacity: 1, scale: 1 }}
                          viewport={{ once: true, amount: 0.5 }}
                          transition={{ duration: 0.28, delay: 0.02 + rowIndex * 0.01 }}
                          className="rounded-xl border px-4 py-3 text-center text-sm text-app-text shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_0_18px_rgba(15,216,255,0.04)]"
                          style={{
                            borderColor: `rgba(255,255,255,${0.08 + opacity * 0.14})`,
                            background: `linear-gradient(135deg, rgba(15,216,255,${baseOpacity}), rgba(216,186,103,${0.06 + opacity * 0.18}))`,
                          }}
                        >
                          {entry.valueLabel ??
                            (typeof entry.value === "number"
                              ? formatNumber(entry.value)
                              : "n/a")}
                        </motion.div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </ChartFrame>
  );
}
