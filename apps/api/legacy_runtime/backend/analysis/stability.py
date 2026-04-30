"""Lightweight run-to-run stability helpers.

These utilities compare repeated simulation outputs from the same setup.
The goal is demo-friendly repeatability checks, not statistical inference.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

import pandas as pd

from backend.analysis.findings import assess_question_trust
from backend.schemas import MockResponseRecord, PersonaProfile


USE_CASE_KEYWORDS = ["use case", "use-case", "usage", "purpose", "room"]
BARRIER_KEYWORDS = ["barrier", "challenge", "concern", "obstacle", "cost", "constraint", "blocker"]
INTEREST_KEYWORDS = ["interest", "interested", "likelihood", "likely", "adopt", "purchase", "buy"]
FEASIBILITY_KEYWORDS = ["feasible", "feasibility", "practical", "practicable", "realistic"]


def summarize_run_outputs(
	records: Iterable[MockResponseRecord],
	personas: Iterable[PersonaProfile] | None = None,
) -> dict[str, Any]:
	"""Extract a compact metric summary for one run."""
	records_df = _records_to_dataframe(records)
	personas_df = _personas_to_dataframe(personas)

	top_use_case = _top_signal_answer(records_df, USE_CASE_KEYWORDS)
	top_barrier = _top_signal_answer(records_df, BARRIER_KEYWORDS)
	strongest_segment = _top_segment(records_df)

	avg_interest = _average_numeric_signal(records_df, INTEREST_KEYWORDS)
	avg_feasibility = _average_numeric_signal(records_df, FEASIBILITY_KEYWORDS)

	if top_use_case is None and not personas_df.empty and "likely_use_case" in personas_df.columns:
		top_use_case = _top_series_value(personas_df["likely_use_case"])
	if top_barrier is None and not personas_df.empty and "likely_barrier" in personas_df.columns:
		top_barrier = _top_series_value(personas_df["likely_barrier"])
	if strongest_segment is None and not personas_df.empty and "segment_label" in personas_df.columns:
		strongest_segment = _top_series_value(personas_df["segment_label"])

	confidence_label = _overall_confidence_label(records_df)

	return {
		"top_use_case": top_use_case,
		"avg_interest": avg_interest,
		"avg_feasibility": avg_feasibility,
		"top_barrier": top_barrier,
		"strongest_segment": strongest_segment,
		"confidence_label": confidence_label,
	}


def build_stability_table(run_summaries: list[dict[str, Any]]) -> pd.DataFrame:
	"""Build a compact table comparing run-level metrics and stability labels."""
	if not run_summaries:
		return pd.DataFrame(columns=["metric_name", "stability_label"])

	metric_names = [
		"top_use_case",
		"avg_interest",
		"avg_feasibility",
		"top_barrier",
		"strongest_segment",
		"confidence_label",
	]

	rows: list[dict[str, Any]] = []
	run_count = len(run_summaries)
	for metric_name in metric_names:
		values = [summary.get(metric_name) for summary in run_summaries]
		row: dict[str, Any] = {
			"metric_name": metric_name,
			"stability_label": _stability_label(metric_name, values),
		}
		for index, value in enumerate(values, start=1):
			row[f"run_{index}"] = value
		rows.append(row)

	columns = ["metric_name", *[f"run_{i}" for i in range(1, run_count + 1)], "stability_label"]
	return pd.DataFrame(rows)[columns]


def _records_to_dataframe(records: Iterable[MockResponseRecord]) -> pd.DataFrame:
	rows: list[dict[str, Any]] = []
	for record in records:
		if hasattr(record, "model_dump"):
			rows.append(record.model_dump())
		elif isinstance(record, dict):
			rows.append(record)
	return pd.DataFrame(rows)


def _personas_to_dataframe(personas: Iterable[PersonaProfile] | None) -> pd.DataFrame:
	if personas is None:
		return pd.DataFrame()
	rows: list[dict[str, Any]] = []
	for persona in personas:
		if hasattr(persona, "model_dump"):
			rows.append(persona.model_dump())
		elif isinstance(persona, dict):
			rows.append(persona)
	return pd.DataFrame(rows)


def _top_signal_answer(df: pd.DataFrame, keywords: list[str]) -> str | None:
	if df.empty:
		return None
	if not {"question_text", "answer", "question_type"}.issubset(df.columns):
		return None

	text_series = df["question_text"].fillna("").astype(str).str.lower()
	mask = text_series.apply(lambda txt: any(keyword in txt for keyword in keywords))
	qdf = df[mask].copy()
	if qdf.empty:
		return None

	qdf = qdf[qdf["question_type"].isin(["single_choice", "multi_choice"])]
	if qdf.empty:
		return None

	if (qdf["question_type"] == "multi_choice").any():
		qdf = qdf.explode("answer")

	answers = qdf["answer"].dropna().astype(str).str.strip()
	answers = answers[answers != ""]
	return _top_series_value(answers)


def _average_numeric_signal(df: pd.DataFrame, keywords: list[str]) -> float | None:
	if df.empty:
		return None
	if not {"question_text", "answer", "question_type"}.issubset(df.columns):
		return None

	text_series = df["question_text"].fillna("").astype(str).str.lower()
	mask = text_series.apply(lambda txt: any(keyword in txt for keyword in keywords))
	qdf = df[mask].copy()
	if qdf.empty:
		return None

	qdf = qdf[qdf["question_type"].isin(["likert", "numeric"])]
	if qdf.empty:
		return None

	numeric = pd.to_numeric(qdf["answer"], errors="coerce").dropna()
	if numeric.empty:
		return None
	return float(round(float(numeric.mean()), 4))


def _top_segment(df: pd.DataFrame) -> str | None:
	if df.empty or "segment_label" not in df.columns:
		return None
	segment_series = df["segment_label"].dropna().astype(str).str.strip()
	segment_series = segment_series[segment_series != ""]
	return _top_series_value(segment_series)


def _overall_confidence_label(df: pd.DataFrame) -> str | None:
	if df.empty or "question_id" not in df.columns:
		return None

	labels: list[str] = []
	for question_id in sorted(df["question_id"].dropna().astype(str).unique().tolist()):
		trust = assess_question_trust(df, question_id)
		label = trust.get("confidence_label")
		if label:
			labels.append(str(label))

	if not labels:
		return None
	return Counter(labels).most_common(1)[0][0]


def _top_series_value(series: pd.Series) -> str | None:
	if series.empty:
		return None
	counts = series.value_counts()
	if counts.empty:
		return None
	return str(counts.index[0])


def _stability_label(metric_name: str, values: list[Any]) -> str:
	cleaned = [value for value in values if value is not None]
	if len(cleaned) <= 1:
		return "stable"

	if metric_name in {"avg_interest", "avg_feasibility"}:
		numeric_values = [float(value) for value in cleaned]
		spread = max(numeric_values) - min(numeric_values)
		if spread <= 0.25:
			return "stable"
		if spread <= 0.75:
			return "mostly_stable"
		return "unstable"

	counts = Counter(str(value) for value in cleaned)
	unique_count = len(counts)
	top_count = counts.most_common(1)[0][1]

	if unique_count == 1:
		return "stable"
	if top_count >= len(cleaned) - 1:
		return "mostly_stable"
	return "unstable"
