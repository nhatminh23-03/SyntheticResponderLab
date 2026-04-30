"""Basic segment/model helpers for analysis filters."""

from __future__ import annotations

import pandas as pd


def list_models(df: pd.DataFrame) -> list[str]:
	"""Return sorted model values present in the dataset."""
	if df.empty or "model" not in df.columns:
		return []
	return sorted(df["model"].dropna().astype(str).unique().tolist())


def list_segments(df: pd.DataFrame) -> list[str]:
	"""Return sorted segment labels present in the dataset."""
	if df.empty or "segment_label" not in df.columns:
		return []
	return sorted(df["segment_label"].dropna().astype(str).unique().tolist())
