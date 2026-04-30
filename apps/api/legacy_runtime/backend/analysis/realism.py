"""Offline realism scorecard helpers for synthetic-vs-real comparison.

This module intentionally keeps real survey outcomes out of runtime generation.
It is for calibration/evaluation only, using saved mock/live records after a run.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from backend.schemas import MockResponseRecord


def load_realism_targets_file(targets_path: str | Path) -> dict[str, Any]:
    """Load and normalize realism targets from a JSON file."""
    path = Path(targets_path)
    if not path.exists():
        raise FileNotFoundError(f"Targets file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Targets payload must be a JSON object.")

    question_targets = payload.get("question_targets", [])
    if not isinstance(question_targets, list):
        raise ValueError("question_targets must be a list.")

    normalized_targets: list[dict[str, Any]] = []
    for item in question_targets:
        if not isinstance(item, Mapping):
            continue
        distribution = _normalize_distribution(item.get("distribution", {}))
        if not distribution:
            continue

        weight = _safe_float(item.get("weight"), default=1.0)
        normalized_targets.append(
            {
                "question_id": _clean_text(item.get("question_id")),
                "question_text_contains": _clean_text(item.get("question_text_contains")),
                "distribution": distribution,
                "weight": max(0.0, weight),
                "notes": _clean_text(item.get("notes")),
            }
        )

    payload["question_targets"] = normalized_targets
    return payload


def evaluate_realism_scorecard(
    records: list[MockResponseRecord] | list[dict[str, Any]],
    targets_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare synthetic answer distributions against real-survey target distributions."""
    df = _records_to_dataframe(records)
    question_targets = list(targets_payload.get("question_targets", []))

    if df.empty:
        return {
            "summary": {
                "questions_scored": 0,
                "weighted_tv_distance": None,
                "weighted_js_divergence": None,
                "realism_score_0_to_100": None,
                "message": "No records available for realism scoring.",
            },
            "question_rows": [],
            "question_table": pd.DataFrame(),
        }

    rows: list[dict[str, Any]] = []
    weight_sum = 0.0
    weighted_tv_sum = 0.0
    weighted_js_sum = 0.0

    for target in question_targets:
        row = _score_one_question_target(df, target)
        if row is None:
            continue
        rows.append(row)
        weight = float(row.get("weight", 1.0))
        tv_distance = float(row.get("tv_distance", 0.0))
        js_divergence = float(row.get("js_divergence", 0.0))
        weight_sum += weight
        weighted_tv_sum += weight * tv_distance
        weighted_js_sum += weight * js_divergence

    if weight_sum > 0:
        weighted_tv_distance = weighted_tv_sum / weight_sum
        weighted_js_divergence = weighted_js_sum / weight_sum
        realism_score = max(0.0, 100.0 * (1.0 - weighted_tv_distance))
    else:
        weighted_tv_distance = None
        weighted_js_divergence = None
        realism_score = None

    question_table = pd.DataFrame(rows)
    if not question_table.empty:
        for col in ["tv_distance", "js_divergence", "synthetic_n", "weight"]:
            if col in question_table.columns:
                question_table[col] = pd.to_numeric(question_table[col], errors="coerce")

    summary = {
        "questions_scored": int(len(rows)),
        "weighted_tv_distance": _round_or_none(weighted_tv_distance, digits=4),
        "weighted_js_divergence": _round_or_none(weighted_js_divergence, digits=4),
        "realism_score_0_to_100": _round_or_none(realism_score, digits=2),
        "message": (
            "Lower distance is better. Higher realism score is better. "
            "This calibration runs offline and is never injected into runtime prompting."
        ),
    }

    return {
        "summary": summary,
        "question_rows": rows,
        "question_table": question_table,
    }


def _score_one_question_target(df: pd.DataFrame, target: Mapping[str, Any]) -> dict[str, Any] | None:
    question_id = _clean_text(target.get("question_id"))
    question_text_contains = _clean_text(target.get("question_text_contains"))
    target_distribution = _normalize_distribution(target.get("distribution", {}))
    if not target_distribution:
        return None

    filtered_df = _filter_question_rows(
        df=df,
        question_id=question_id,
        question_text_contains=question_text_contains,
    )
    synthetic_distribution = _compute_answer_distribution(filtered_df)

    if not synthetic_distribution:
        return {
            "question_id": question_id,
            "question_text_contains": question_text_contains,
            "synthetic_n": 0,
            "tv_distance": 1.0,
            "js_divergence": 1.0,
            "weight": float(target.get("weight", 1.0) or 1.0),
            "notes": _clean_text(target.get("notes")),
        }

    support = sorted(set(target_distribution.keys()) | set(synthetic_distribution.keys()))
    p = [float(target_distribution.get(k, 0.0)) for k in support]
    q = [float(synthetic_distribution.get(k, 0.0)) for k in support]

    tv_distance = _tv_distance(p, q)
    js_divergence = _js_divergence(p, q)

    return {
        "question_id": question_id,
        "question_text_contains": question_text_contains,
        "synthetic_n": int(len(filtered_df)),
        "tv_distance": float(tv_distance),
        "js_divergence": float(js_divergence),
        "weight": float(target.get("weight", 1.0) or 1.0),
        "notes": _clean_text(target.get("notes")),
    }


def _records_to_dataframe(records: list[MockResponseRecord] | list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        if hasattr(record, "model_dump"):
            rows.append(record.model_dump())
        elif isinstance(record, Mapping):
            rows.append(dict(record))
    return pd.DataFrame(rows)


def _filter_question_rows(
    *,
    df: pd.DataFrame,
    question_id: str | None,
    question_text_contains: str | None,
) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()
    if question_id and "question_id" in filtered.columns:
        filtered = filtered[filtered["question_id"].astype(str) == question_id]

    if question_text_contains and "question_text" in filtered.columns:
        keyword = str(question_text_contains).lower()
        filtered = filtered[
            filtered["question_text"].fillna("").astype(str).str.lower().str.contains(keyword)
        ]

    return filtered


def _compute_answer_distribution(question_df: pd.DataFrame) -> dict[str, float]:
    if question_df.empty or "answer" not in question_df.columns:
        return {}

    expanded_answers: list[str] = []
    for _, row in question_df.iterrows():
        answer = row.get("answer")
        if isinstance(answer, list):
            for item in answer:
                text = _clean_text(item)
                if text:
                    expanded_answers.append(text)
        else:
            text = _clean_text(answer)
            if text:
                expanded_answers.append(text)

    if not expanded_answers:
        return {}

    counts = pd.Series(expanded_answers).value_counts(dropna=False)
    total = float(counts.sum())
    if total <= 0:
        return {}

    return {str(answer): float(count / total) for answer, count in counts.items()}


def _normalize_distribution(payload: Any) -> dict[str, float]:
    if not isinstance(payload, Mapping):
        return {}

    cleaned: dict[str, float] = {}
    for raw_key, raw_value in payload.items():
        key = _clean_text(raw_key)
        if not key:
            continue
        value = _safe_float(raw_value)
        if value is None or value < 0:
            continue
        cleaned[key] = value

    if not cleaned:
        return {}

    total = sum(cleaned.values())
    if total <= 0:
        return {}

    # Accept either shares (sum≈1) or percentages (sum≈100).
    if total > 1.5:
        return {key: value / total for key, value in cleaned.items()}
    return {key: value / total for key, value in cleaned.items()}


def _tv_distance(p: list[float], q: list[float]) -> float:
    if not p or not q or len(p) != len(q):
        return 1.0
    return 0.5 * sum(abs(a - b) for a, b in zip(p, q))


def _js_divergence(p: list[float], q: list[float]) -> float:
    if not p or not q or len(p) != len(q):
        return 1.0

    m = [(a + b) / 2.0 for a, b in zip(p, q)]
    return 0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m)


def _kl_divergence(p: list[float], q: list[float]) -> float:
    eps = 1e-12
    score = 0.0
    for pi, qi in zip(p, q):
        p_adj = max(eps, float(pi))
        q_adj = max(eps, float(qi))
        score += p_adj * math.log(p_adj / q_adj, 2)
    return float(score)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return float(round(float(value), digits))
