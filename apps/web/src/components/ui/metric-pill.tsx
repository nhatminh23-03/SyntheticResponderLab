type MetricPillProps = {
  value: string;
  label: string;
  accent?: "cyan" | "gold";
};

export function MetricPill({
  value,
  label,
  accent = "cyan",
}: MetricPillProps) {
  return (
    <div
      className="rounded-2xl border px-4 py-3 backdrop-blur-md"
      style={{
        background: "var(--metric-pill-bg)",
        borderColor: "var(--metric-pill-border)",
      }}
    >
      <div
        className={
          accent === "gold"
            ? "text-lg font-bold text-app-gold"
            : "text-lg font-bold text-app-cyan"
        }
      >
        {value}
      </div>
      <div className="mt-1 text-[0.68rem] uppercase tracking-[0.22em] text-app-muted">
        {label}
      </div>
    </div>
  );
}
