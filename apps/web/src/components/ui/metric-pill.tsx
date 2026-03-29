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
    <div className="rounded-2xl border border-white/6 bg-white/[0.03] px-4 py-3 backdrop-blur-md">
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
