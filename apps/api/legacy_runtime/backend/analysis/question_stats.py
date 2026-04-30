"""Basic question-level helpers for mock record analysis."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from backend.storage import load_mock_response_records


def load_mock_records_dataframe() -> pd.DataFrame:
	"""Load mock response records from storage into a pandas DataFrame.

	Returns an empty DataFrame when no records are available.
	"""
	records = load_mock_response_records()
	if not records:
		return pd.DataFrame()
	return pd.DataFrame([record.model_dump() for record in records])


def compute_dataset_summary(df: pd.DataFrame) -> Dict[str, object]:
	"""Compute lightweight dataset summary metrics."""
	if df.empty:
		return {
			"total_records": 0,
			"unique_respondents": 0,
			"question_count": 0,
			"models_present": [],
			"segments_present": [],
			"survey_titles_present": [],
		}

	return {
		"total_records": int(len(df)),
		"unique_respondents": int(df["respondent_id"].nunique()),
		"question_count": int(df["question_id"].nunique()),
		"models_present": sorted(df["model"].dropna().astype(str).unique().tolist()),
		"segments_present": sorted(df["segment_label"].dropna().astype(str).unique().tolist()),
		"survey_titles_present": sorted(df["survey_title"].dropna().astype(str).unique().tolist()),
	}


def apply_record_filters(
	df: pd.DataFrame,
	model: Optional[str] = None,
	segment_label: Optional[str] = None,
) -> pd.DataFrame:
	"""Filter records by model and/or segment label."""
	if df.empty:
		return df

	filtered = df.copy()
	if model and model != "All":
		filtered = filtered[filtered["model"] == model]
	if segment_label and segment_label != "All":
		filtered = filtered[filtered["segment_label"] == segment_label]
	return filtered


def compute_question_answer_distribution(df: pd.DataFrame, question_id: str) -> pd.DataFrame:
	"""Compute answer counts and percentages for a single question."""
	if df.empty:
		return pd.DataFrame(columns=["answer_display", "count", "percentage"])

	question_df = df[df["question_id"] == question_id].copy()
	if question_df.empty:
		return pd.DataFrame(columns=["answer_display", "count", "percentage"])

	# Multi-choice answers may be lists; explode for per-option counts.
	if question_df["question_type"].iloc[0] == "multi_choice":
		question_df = question_df.explode("answer")

	answer_series = question_df["answer"].astype(str).fillna("None")
	counts = answer_series.value_counts(dropna=False).rename_axis("answer_display").reset_index(name="count")
	total = counts["count"].sum()
	counts["percentage"] = (counts["count"] / total * 100).round(1) if total else 0.0
	return counts


def get_example_open_text_responses(df: pd.DataFrame, question_id: str, limit: int = 10) -> pd.DataFrame:
	"""Return a small sample of open-text responses for a question."""
	if df.empty:
		return pd.DataFrame(columns=["respondent_id", "model", "segment_label", "answer"])

	question_df = df[df["question_id"] == question_id].copy()
	if question_df.empty:
		return pd.DataFrame(columns=["respondent_id", "model", "segment_label", "answer"])

	open_text_df = question_df[["respondent_id", "model", "segment_label", "answer"]].head(limit)
	return open_text_df
