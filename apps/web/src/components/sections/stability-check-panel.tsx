"use client";

import { useEffect, useState } from "react";

import {
  getLatestStabilityCheck,
  SimulationJobPayload,
  SimulationStabilityResultPayload,
  startStabilityCheck,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { BadgeChip } from "@/components/ui/badge-chip";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass-panel";

type StatusTone = "neutral" | "success" | "warning" | "error";

type StatusState = {
  tone: StatusTone;
  message: string;
};

const EMPTY_STATUS: StatusState = {
  tone: "neutral",
  message: "Use Stability Check to measure repeatability after the main run.",
};

export function StabilityCheckPanel({ studyId }: { studyId?: string | null }) {
  const [latestStabilityCheck, setLatestStabilityCheck] =
    useState<SimulationJobPayload<SimulationStabilityResultPayload> | null>(null);
  const [status, setStatus] = useState<StatusState>(EMPTY_STATUS);
  const [isRunning, setIsRunning] = useState(false);
  const [repeatRuns, setRepeatRuns] = useState(2);

  useEffect(() => {
    let cancelled = false;

    async function hydrateStabilityState() {
      if (!studyId) {
        if (!cancelled) {
          setLatestStabilityCheck(null);
          setStatus(EMPTY_STATUS);
        }
        return;
      }

      try {
        const result = await getLatestStabilityCheck(studyId);
        if (cancelled) {
          return;
        }
        setLatestStabilityCheck(result);
        setStatus(buildStabilityStatus(result));
      } catch (error) {
        if (!cancelled) {
          setStatus({
            tone: "error",
            message:
              error instanceof Error
                ? error.message
                : "Unable to load the stability check right now.",
          });
        }
      }
    }

    void hydrateStabilityState();

    return () => {
      cancelled = true;
    };
  }, [studyId]);

  async function handleRunStabilityCheck() {
    if (!studyId) {
      setStatus({
        tone: "warning",
        message: "Complete the main study run first, then launch a stability check.",
      });
      return;
    }

    setIsRunning(true);
    setStatus({
      tone: "neutral",
      message: "Running repeatability checks. This can take a few minutes on live models...",
    });

    try {
      const result = await startStabilityCheck(studyId, repeatRuns);
      setLatestStabilityCheck(result);
      setStatus(buildStabilityStatus(result));
    } catch (error) {
      setStatus({
        tone: "error",
        message:
          error instanceof Error
            ? error.message
            : "Unable to run the stability check right now.",
      });
    } finally {
      setIsRunning(false);
    }
  }

  const stabilityRows = latestStabilityCheck?.result?.stability_table ?? [];

  return (
    <GlassPanel className="p-5 sm:p-6">
      <div className="rounded-[1.55rem] border border-app-border [background:var(--theme-panel-gradient)] p-5">
        <div className="flex flex-wrap items-center gap-3">
          <BadgeChip tone="gold">Stability Check</BadgeChip>
          <BadgeChip>Repeatability</BadgeChip>
        </div>
        <p className="mt-4 text-sm leading-6 text-app-muted">
          Run this after the main study to check whether the same setup produces stable patterns
          across repeated executions.
        </p>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <NumberStepper
            label="Repeat runs"
            value={repeatRuns}
            min={2}
            max={5}
            onChange={setRepeatRuns}
          />
          <Button variant="secondary" onClick={handleRunStabilityCheck} disabled={isRunning}>
            {isRunning ? "Running Stability Check..." : "Run Stability Check"}
          </Button>
        </div>

        <div className="mt-5">
          <StatusBanner tone={status.tone} message={status.message} />
        </div>

        {stabilityRows.length > 0 ? (
          <div className="mt-5 rounded-[1.35rem] border border-app-border [background:var(--status-neutral-bg)] p-4">
            <StabilityTable rows={stabilityRows} />
          </div>
        ) : null}
      </div>
    </GlassPanel>
  );
}

function buildStabilityStatus(
  latestStabilityCheck: SimulationJobPayload<SimulationStabilityResultPayload> | null
): StatusState {
  if (!latestStabilityCheck?.result) {
    return EMPTY_STATUS;
  }

  const unstableCount =
    latestStabilityCheck.result.stability_labels?.filter((label) => label === "unstable")
      .length ?? 0;
  if (unstableCount > 0) {
    return {
      tone: "warning",
      message: `Stability check completed with ${unstableCount} unstable metric${unstableCount === 1 ? "" : "s"}.`,
    };
  }

  return {
    tone: "success",
    message: "Stability check completed and saved.",
  };
}

function StatusBanner({ tone, message }: { tone: StatusTone; message: string }) {
  return (
    <div
      className={cn(
        "rounded-[1.35rem] border px-5 py-4 text-sm leading-6",
        tone === "success" &&
          "[border-color:var(--status-success-border)] [background:var(--status-success-bg)] [color:var(--status-success-text)]",
        tone === "warning" &&
          "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
        tone === "error" &&
          "[border-color:var(--status-warning-border)] [background:var(--status-warning-bg)] [color:var(--status-warning-text)]",
        tone === "neutral" &&
          "border-app-border [background:var(--status-neutral-bg)] text-app-muted"
      )}
    >
      {message}
    </div>
  );
}

function NumberStepper({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="inline-flex items-center gap-3 rounded-[1.2rem] border border-app-border [background:var(--status-neutral-bg)] px-3 py-2">
      <span className="text-sm text-app-muted">{label}</span>
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-app-border [background:var(--control-bg)] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
      >
        −
      </button>
      <span className="w-6 text-center text-sm text-app-text">{value}</span>
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-app-border [background:var(--control-bg)] text-app-text transition hover:border-app-cyan/25 hover:text-app-cyan"
      >
        +
      </button>
    </div>
  );
}

function StabilityTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const runColumns = Array.from(
    new Set(rows.flatMap((row) => Object.keys(row).filter((key) => key.startsWith("run_"))))
  ).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-y-3">
        <thead>
          <tr className="text-left">
            <th className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
              Metric
            </th>
            <th className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
              Status
            </th>
            {runColumns.map((column) => (
              <th
                key={column}
                className="px-3 pb-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted"
              >
                {humanizeRunColumn(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${String(row.metric_name ?? index)}-${index}`}>
              <td className="rounded-l-[1rem] border border-app-border border-r-0 [background:var(--status-neutral-bg)] px-3 py-3 text-sm text-app-text">
                {humanizeMetricName(row.metric_name, index)}
              </td>
              <td className="border border-app-border border-l-0 border-r-0 [background:var(--status-neutral-bg)] px-3 py-3">
                <BadgeChip
                  tone={
                    row.stability_label === "stable"
                      ? "cyan"
                      : row.stability_label === "mostly_stable"
                        ? "gold"
                        : "gold"
                  }
                >
                  {humanizeToken(toOptionalString(row.stability_label) || "unknown")}
                </BadgeChip>
              </td>
              {runColumns.map((column, runIndex) => (
                <td
                  key={`${String(row.metric_name ?? index)}-${column}`}
                  className={cn(
                    "border border-app-border border-l-0 [background:var(--status-neutral-bg)] px-3 py-3 text-sm leading-6 text-app-muted",
                    runIndex === runColumns.length - 1 && "rounded-r-[1rem]"
                  )}
                >
                  {formatTableValue(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function humanizeMetricName(value: unknown, index: number) {
  const label = toOptionalString(value);
  if (!label) {
    return `Metric ${index + 1}`;
  }
  return humanizeToken(label);
}

function humanizeRunColumn(value: string) {
  return value.replace("run_", "Run ");
}

function humanizeToken(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTableValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((entry) => String(entry)).join(" • ");
  }
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? String(value)
      : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (value === null || typeof value === "undefined" || value === "") {
    return "n/a";
  }
  return String(value).replaceAll("_", " ");
}

function toOptionalString(value: unknown) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}
