"""Rule-based insight helpers built from mock response records."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def assess_question_trust(df: pd.DataFrame, question_id: str) -> Dict[str, Any]:
	"""Return trust labels and explanation for a single question.

	This helper is intentionally simple, deterministic, and demo-friendly.
	It does not perform statistical inference.
	"""
	default = {
		"question_id": question_id,
		"confidence_label": "Needs validation",
		"agreement_label": "Partial agreement",
		"explanation": "Limited evidence available. Treat as exploratory and validate with real respondents.",
	}

	if df.empty or "question_id" not in df.columns:
		return default

	qdf = df[df["question_id"] == question_id].copy()
	if qdf.empty:
		return default

	question_type = str(qdf["question_type"].iloc[0])
	total_n = int(len(qdf))
	model_count = int(qdf["model"].nunique()) if "model" in qdf.columns else 0

	if question_type == "open_text":
		if total_n >= 10 and model_count >= 2:
			return {
				"question_id": question_id,
				"confidence_label": "Low confidence",
				"agreement_label": "Partial agreement",
				"explanation": "Open-text themes appear in multiple responses, but qualitative summaries remain exploratory.",
			}
		return {
			"question_id": question_id,
			"confidence_label": "Needs validation",
			"agreement_label": "Partial agreement",
			"explanation": "Open-text evidence is directional only. Validate themes with real respondent interviews.",
		}

	if question_type in {"single_choice", "multi_choice"}:
		series = _answer_series(qdf, question_type)
		if series.empty:
			return default

		counts = series.value_counts()
		total = int(counts.sum())
		top_share = float(counts.iloc[0] / total) if total else 0.0
		second_share = float(counts.iloc[1] / total) if len(counts) > 1 and total else 0.0
		margin = top_share - second_share

		agreement_label = _choice_agreement_label(qdf, question_type)

		if total_n < 12 or model_count < 2:
			confidence_label = "Needs validation"
			explanation = "Small sample or limited model coverage. Treat this pattern as exploratory."
		elif agreement_label == "Agreement" and top_share >= 0.60 and margin >= 0.20:
			confidence_label = "High confidence"
			explanation = (
				"One option clearly leads and models share the same top answer. "
				"Signal is stable for hypothesis generation."
			)
		elif agreement_label in {"Agreement", "Partial agreement"} and top_share >= 0.45 and margin >= 0.10:
			confidence_label = "Moderate confidence"
			explanation = (
				"A leading option is present, but separation is moderate. "
				"Use as a directional signal."
			)
		elif agreement_label == "Disagreement":
			confidence_label = "Low confidence"
			explanation = "Models disagree on the top option, so conclusions should be treated cautiously."
		else:
			confidence_label = "Needs validation"
			explanation = "No strong leading pattern is visible yet. Gather more evidence before decisions."

		return {
			"question_id": question_id,
			"confidence_label": confidence_label,
			"agreement_label": agreement_label,
			"explanation": explanation,
		}

	if question_type in {"likert", "numeric"}:
		numeric = pd.to_numeric(qdf["answer"], errors="coerce").dropna()
		if numeric.empty:
			return default

		means = (
			qdf.assign(answer_num=pd.to_numeric(qdf["answer"], errors="coerce"))
			.groupby("model", dropna=True)["answer_num"]
			.mean()
			.dropna()
		)

		if len(means) < 2 or total_n < 12:
			return {
				"question_id": question_id,
				"confidence_label": "Needs validation",
				"agreement_label": "Partial agreement",
				"explanation": "Numeric pattern exists, but sample/model coverage is still limited.",
			}

		diff = float(means.max() - means.min())
		if diff <= 0.35:
			agreement_label = "Agreement"
		elif diff <= 0.90:
			agreement_label = "Partial agreement"
		else:
			agreement_label = "Disagreement"

		if agreement_label == "Agreement" and total_n >= 20:
			confidence_label = "High confidence"
			explanation = "Model averages are close and the sample is reasonably sized for a stable directional read."
		elif agreement_label in {"Agreement", "Partial agreement"}:
			confidence_label = "Moderate confidence"
			explanation = "Model averages are somewhat aligned; treat as a directional, not final, signal."
		elif agreement_label == "Disagreement":
			confidence_label = "Low confidence"
			explanation = "Model averages differ meaningfully, so this finding needs external validation."
		else:
			confidence_label = "Needs validation"
			explanation = "Evidence remains limited for a stable numeric conclusion."

		return {
			"question_id": question_id,
			"confidence_label": confidence_label,
			"agreement_label": agreement_label,
			"explanation": explanation,
		}

	return {
		"question_id": question_id,
		"confidence_label": "Needs validation",
		"agreement_label": "Partial agreement",
		"explanation": "Question type is not covered by trust rules yet. Treat as exploratory.",
	}


def build_question_trust_map(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
	"""Build trust labels and explanations for every question in the dataset."""
	if df.empty or "question_id" not in df.columns:
		return {}

	question_ids = sorted(df["question_id"].dropna().astype(str).unique().tolist())
	return {question_id: assess_question_trust(df, question_id) for question_id in question_ids}


def build_question_findings(df: pd.DataFrame) -> List[Dict[str, Any]]:
	"""Generate simple question-level findings from mock records."""
	if df.empty:
		return []

	findings: List[Dict[str, Any]] = []
	question_meta = df[["question_id", "question_text", "question_type"]].drop_duplicates()

	for _, row in question_meta.iterrows():
		question_id = row["question_id"]
		question_text = row["question_text"]
		question_type = row["question_type"]
		qdf = df[df["question_id"] == question_id].copy()

		finding: Dict[str, Any] = {
			"question_id": question_id,
			"question_text": question_text,
			"question_type": question_type,
		}

		if question_type in {"single_choice", "multi_choice"}:
			top = _top_answer_with_share(qdf, question_type=question_type)
			finding.update(top)

		elif question_type in {"likert", "numeric"}:
			numeric = pd.to_numeric(qdf["answer"], errors="coerce").dropna()
			mean_value = float(numeric.mean()) if not numeric.empty else None
			mode_value = numeric.mode().iloc[0] if not numeric.mode().empty else None
			finding.update(
				{
					"average_value": round(mean_value, 2) if mean_value is not None else None,
					"most_common_value": int(mode_value) if pd.notna(mode_value) else None,
				}
			)

		else:
			samples = (
				qdf["answer"]
				.dropna()
				.astype(str)
				.str.strip()
				.loc[lambda s: s != ""]
				.head(5)
				.tolist()
			)
			finding["sample_responses"] = samples

		findings.append(finding)

	return findings


def build_model_comparison_notes(df: pd.DataFrame) -> List[str]:
	"""Create simple model comparison notes based on top answers by question."""
	if df.empty or "model" not in df.columns:
		return []

	notes: List[str] = []
	for question_id, qdf in df.groupby("question_id"):
		question_text = qdf["question_text"].iloc[0]
		question_type = qdf["question_type"].iloc[0]

		if question_type not in {"single_choice", "multi_choice", "likert", "numeric"}:
			continue

		top_by_model: Dict[str, str] = {}
		for model, mdf in qdf.groupby("model"):
			top_answer = _top_answer_label(mdf, question_type)
			if top_answer is not None:
				top_by_model[model] = top_answer

		unique_tops = set(top_by_model.values())
		if len(top_by_model) < 2:
			continue
		if len(unique_tops) == 1:
			notes.append(f"{question_id}: models agree on top answer '{next(iter(unique_tops))}'.")
		else:
			formatted = ", ".join([f"{model} → {answer}" for model, answer in top_by_model.items()])
			notes.append(f"{question_id}: model differences observed ({formatted}).")

	if not notes:
		notes.append("No notable model differences found in current mock records.")
	return notes


def build_segment_comparison_notes(df: pd.DataFrame) -> List[str]:
	"""Create simple segment comparison notes based on top answers by segment."""
	if df.empty or "segment_label" not in df.columns:
		return []

	notes: List[str] = []
	segment_df = df.dropna(subset=["segment_label"])
	if segment_df.empty:
		return ["No segment labels found in current mock records."]

	for question_id, qdf in segment_df.groupby("question_id"):
		question_type = qdf["question_type"].iloc[0]
		if question_type not in {"single_choice", "multi_choice", "likert", "numeric"}:
			continue

		top_by_segment: Dict[str, str] = {}
		for segment, sdf in qdf.groupby("segment_label"):
			top_answer = _top_answer_label(sdf, question_type)
			if top_answer is not None:
				top_by_segment[str(segment)] = top_answer

		if len(top_by_segment) < 2:
			continue

		unique_tops = set(top_by_segment.values())
		if len(unique_tops) == 1:
			notes.append(f"{question_id}: segments show similar top answer '{next(iter(unique_tops))}'.")
		else:
			formatted = ", ".join([f"{seg} → {ans}" for seg, ans in top_by_segment.items()])
			notes.append(f"{question_id}: segment differences observed ({formatted}).")

	if not notes:
		notes.append("No strong segment differences found in current mock records.")
	return notes


def build_rule_based_recommendations(
	question_findings: List[Dict[str, Any]],
	model_notes: List[str],
	segment_notes: List[str],
) -> List[str]:
	"""Generate a short deterministic recommendation list."""
	recommendations = [
		"Prioritize the strongest-performing use case signal in the next product concept iteration.",
		"Validate key signals with real respondents before making final product decisions.",
	]

	if any("differences observed" in note for note in model_notes):
		recommendations.append("Inspect model-to-model differences before drawing directional conclusions.")
	else:
		recommendations.append("Model agreement is encouraging, but still validate with real-user research.")

	if any("differences observed" in note for note in segment_notes):
		recommendations.append("Segment-specific patterns suggest targeted messaging or feature positioning.")

	if any(finding.get("question_type") == "open_text" for finding in question_findings):
		recommendations.append("Review open-text comments for qualitative themes to guide follow-up interviews.")

	# Keep the list concise.
	return recommendations[:5]


def _top_answer_with_share(qdf: pd.DataFrame, question_type: str) -> Dict[str, Any]:
	"""Return top answer, count, and share for choice-like questions."""
	series = _answer_series(qdf, question_type)
	if series.empty:
		return {"top_answer": None, "top_count": 0, "top_percentage": 0.0}

	counts = series.value_counts()
	top_answer = str(counts.index[0])
	top_count = int(counts.iloc[0])
	top_percentage = round(top_count / int(counts.sum()) * 100, 1)
	return {"top_answer": top_answer, "top_count": top_count, "top_percentage": top_percentage}


def _top_answer_label(qdf: pd.DataFrame, question_type: str) -> str | None:
	"""Return top answer label for comparison notes."""
	top = _top_answer_with_share(qdf, question_type)
	return top.get("top_answer")


def _answer_series(qdf: pd.DataFrame, question_type: str) -> pd.Series:
	"""Normalize answer series, exploding multi-choice answers when needed."""
	if question_type == "multi_choice":
		exploded = qdf.explode("answer")
		return exploded["answer"].dropna().astype(str)
	return qdf["answer"].dropna().astype(str)


def _choice_agreement_label(qdf: pd.DataFrame, question_type: str) -> str:
	"""Compute Agreement/Partial agreement/Disagreement for choice-style questions."""
	if "model" not in qdf.columns:
		return "Partial agreement"

	top_by_model: Dict[str, str] = {}
	for model, mdf in qdf.groupby("model"):
		series = _answer_series(mdf, question_type)
		if series.empty:
			continue
		counts = series.value_counts()
		top_by_model[str(model)] = str(counts.index[0])

	if len(top_by_model) < 2:
		return "Partial agreement"

	unique_tops = set(top_by_model.values())
	if len(unique_tops) == 1:
		return "Agreement"
	if len(unique_tops) < len(top_by_model):
		return "Partial agreement"
	return "Disagreement"
