"""Lightweight benchmark helpers for simulation configuration comparisons.

This module is intentionally compact and demo-focused. It compares multiple
configuration runs and returns readable tables/recommendations.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from backend.analysis.stability import build_stability_table


def build_benchmark_rows(
    *,
    benchmark_name: str,
    configuration_name: str,
    mode_flags: dict[str, Any],
    run_ids: list[str],
    run_summaries: list[dict[str, Any]],
    notes: str = "",
) -> list[dict[str, Any]]:
    """Build compact benchmark result rows for one configuration."""
    if not run_summaries:
        return []

    stability_df = build_stability_table(run_summaries)
    stability_summary = summarize_stability_labels(stability_df)

    rows: list[dict[str, Any]] = []
    for index, summary in enumerate(run_summaries):
        run_id = run_ids[index] if index < len(run_ids) else f"RUN_{index+1:03d}"
        confidence = summary.get("confidence_label")
        confidence_summary = str(confidence) if confidence is not None else "unknown"

        rows.append(
            {
                "benchmark_name": benchmark_name,
                "configuration_name": configuration_name,
                "run_id": run_id,
                "mode_flags": dict(mode_flags),
                "top_use_case": summary.get("top_use_case"),
                "avg_interest": summary.get("avg_interest"),
                "avg_feasibility": summary.get("avg_feasibility"),
                "top_barrier": summary.get("top_barrier"),
                "strongest_segment": summary.get("strongest_segment"),
                "confidence_summary": confidence_summary,
                "stability_label_summary": stability_summary,
                "notes": notes,
            }
        )

    return rows


def build_benchmark_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Create a demo-friendly benchmark table."""
    columns = [
        "benchmark_name",
        "configuration_name",
        "run_id",
        "mode_flags",
        "top_use_case",
        "avg_interest",
        "avg_feasibility",
        "top_barrier",
        "strongest_segment",
        "confidence_summary",
        "stability_label_summary",
        "notes",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    for column in columns:
        if column not in df.columns:
            df[column] = None

    df["avg_interest"] = pd.to_numeric(df["avg_interest"], errors="coerce").round(3)
    df["avg_feasibility"] = pd.to_numeric(df["avg_feasibility"], errors="coerce").round(3)

    # Render mode flags as compact text for readability in UI.
    df["mode_flags"] = df["mode_flags"].map(_format_mode_flags)

    return df[columns]


def summarize_stability_labels(stability_df: pd.DataFrame) -> str:
    """Collapse stability labels into a compact summary string."""
    if stability_df.empty or "stability_label" not in stability_df.columns:
        return "unknown"

    labels = stability_df["stability_label"].dropna().astype(str).tolist()
    if not labels:
        return "unknown"

    counts = Counter(labels)
    order = ["stable", "mostly_stable", "unstable"]
    parts = [f"{label}:{counts.get(label, 0)}" for label in order if label in counts]
    # Include unknown future labels as well.
    for label in sorted(counts.keys()):
        if label not in order:
            parts.append(f"{label}:{counts[label]}")
    return ", ".join(parts)


def recommend_benchmark_modes(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Return compact recommendation labels from benchmark rows."""
    if not rows:
        return {
            "most_stable_mode": "n/a",
            "most_constrained_mode": "n/a",
            "most_affordability_sensitive_mode": "n/a",
        }

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("configuration_name", "unknown"))].append(row)

    def stability_score(group_rows: list[dict[str, Any]]) -> float:
        # score from stability summary: stable=2, mostly_stable=1, unstable=0
        text = str(group_rows[0].get("stability_label_summary", ""))
        parts = _parse_label_summary(text)
        return 2.0 * parts.get("stable", 0) + 1.0 * parts.get("mostly_stable", 0)

    def constrained_score(group_rows: list[dict[str, Any]]) -> float:
        # Higher = more constrained. Lower feasibility/interest implies more constrained.
        feasibility = [float(v) for v in _numeric_values(group_rows, "avg_feasibility")]
        interest = [float(v) for v in _numeric_values(group_rows, "avg_interest")]
        mean_feasibility = sum(feasibility) / len(feasibility) if feasibility else 0.0
        mean_interest = sum(interest) / len(interest) if interest else 0.0
        return (5.0 - mean_feasibility) + (5.0 - mean_interest)

    def affordability_score(group_rows: list[dict[str, Any]]) -> float:
        # Cost-like top barriers indicate stronger affordability sensitivity.
        cost_hits = 0
        for row in group_rows:
            barrier = str(row.get("top_barrier") or "").lower()
            if any(token in barrier for token in ["cost", "price", "budget", "afford"]):
                cost_hits += 1
        return cost_hits / max(1, len(group_rows))

    config_names = list(grouped.keys())

    most_stable = max(config_names, key=lambda name: (stability_score(grouped[name]), -constrained_score(grouped[name])))
    most_constrained = max(config_names, key=lambda name: constrained_score(grouped[name]))
    most_affordability_sensitive = max(config_names, key=lambda name: affordability_score(grouped[name]))

    return {
        "most_stable_mode": most_stable,
        "most_constrained_mode": most_constrained,
        "most_affordability_sensitive_mode": most_affordability_sensitive,
    }


def _format_mode_flags(flags: dict[str, Any]) -> str:
    if not isinstance(flags, dict):
        return str(flags)
    ordered_keys = ["grounded", "geography_filtered", "cex_affordability", "repeats"]
    keys = ordered_keys + [key for key in flags.keys() if key not in ordered_keys]
    rendered = []
    for key in keys:
        if key in flags:
            rendered.append(f"{key}={flags[key]}")
    return ", ".join(rendered)


def _parse_label_summary(text: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for chunk in str(text).split(","):
        part = chunk.strip()
        if not part or ":" not in part:
            continue
        label, value = part.split(":", 1)
        try:
            parsed[label.strip()] = int(value.strip())
        except Exception:
            continue
    return parsed


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        try:
            if value is not None:
                values.append(float(value))
        except Exception:
            continue
    return values
