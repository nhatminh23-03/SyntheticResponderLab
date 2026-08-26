"""Fidelity metrics for the persona-model bake-off.

Real distributions are always weighted by WGTP; synthetic samples are unweighted (each drawn row
counts once). Every metric is oriented so that lower is better, except C2ST AUC where the target is
0.5 and the reported score is |AUC - 0.5|.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split


def weighted_distribution(values: pd.Series, weights: np.ndarray, categories: list) -> np.ndarray:
    """Weighted probability vector over a fixed category order."""
    grouped = pd.Series(weights).groupby(values.astype(str).values).sum()
    probabilities = grouped.reindex(categories).fillna(0.0).values
    total = probabilities.sum()
    return probabilities / total if total else probabilities


def total_variation_distance(p: np.ndarray, q: np.ndarray) -> float:
    return float(0.5 * np.abs(p - q).sum())


def marginal_tvd(
    real: pd.DataFrame,
    real_weights: np.ndarray,
    synthetic: pd.DataFrame,
    attributes: list[str],
) -> tuple[float, dict[str, float]]:
    """Mean total variation distance across each attribute's marginal."""
    per_attribute: dict[str, float] = {}
    for attribute in attributes:
        categories = sorted(set(real[attribute].astype(str)) | set(synthetic[attribute].astype(str)))
        p = weighted_distribution(real[attribute], real_weights, categories)
        q = weighted_distribution(synthetic[attribute], np.ones(len(synthetic)), categories)
        per_attribute[attribute] = total_variation_distance(p, q)
    return float(np.mean(list(per_attribute.values()))), per_attribute


def cramers_v(a: pd.Series, b: pd.Series, weights: np.ndarray) -> float:
    """Bias-corrected Cramér's V between two categorical series, weight-aware."""
    table = (
        pd.DataFrame({"a": a.astype(str).values, "b": b.astype(str).values, "w": weights})
        .groupby(["a", "b"], observed=True)["w"]
        .sum()
        .unstack(fill_value=0.0)
        .values
    )
    total = table.sum()
    if total <= 0 or min(table.shape) < 2:
        return 0.0

    expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / total
    with np.errstate(divide="ignore", invalid="ignore"):
        chi2 = np.nansum(np.where(expected > 0, (table - expected) ** 2 / expected, 0.0))

    n = total
    phi2 = chi2 / n
    r, k = table.shape
    # Bergsma's bias correction, so tables with many categories are not inflated.
    phi2_corrected = max(0.0, phi2 - (k - 1) * (r - 1) / (n - 1))
    r_corrected = r - (r - 1) ** 2 / (n - 1)
    k_corrected = k - (k - 1) ** 2 / (n - 1)
    denominator = min(r_corrected - 1, k_corrected - 1)
    if denominator <= 0:
        return 0.0
    return float(np.sqrt(phi2_corrected / denominator))


def association_matrix(frame: pd.DataFrame, weights: np.ndarray, attributes: list[str]) -> np.ndarray:
    size = len(attributes)
    matrix = np.zeros((size, size))
    for i, j in itertools.combinations(range(size), 2):
        value = cramers_v(frame[attributes[i]], frame[attributes[j]], weights)
        matrix[i, j] = matrix[j, i] = value
    return matrix


def pairwise_association_error(
    real: pd.DataFrame,
    real_weights: np.ndarray,
    synthetic: pd.DataFrame,
    attributes: list[str],
) -> tuple[float, np.ndarray]:
    """Frobenius distance between the real and synthetic Cramér's V matrices.

    This is the metric that exposes independent sampling: a model that draws attributes
    independently produces a near-zero association matrix regardless of the real one.
    """
    real_matrix = association_matrix(real, real_weights, attributes)
    synthetic_matrix = association_matrix(synthetic, np.ones(len(synthetic)), attributes)
    difference = real_matrix - synthetic_matrix
    return float(np.sqrt((difference**2).sum())), difference


def joint_tvd(
    real: pd.DataFrame,
    real_weights: np.ndarray,
    synthetic: pd.DataFrame,
    attributes: list[str],
) -> float:
    """Total variation distance over the full cross-tabulation of `attributes`."""
    def key(frame: pd.DataFrame) -> pd.Series:
        return frame[attributes].astype(str).agg("|".join, axis=1)

    real_key = key(real)
    synthetic_key = key(synthetic)
    categories = sorted(set(real_key) | set(synthetic_key))
    p = weighted_distribution(real_key, real_weights, categories)
    q = weighted_distribution(synthetic_key, np.ones(len(synthetic)), categories)
    return total_variation_distance(p, q)


def c2st_auc(
    real: pd.DataFrame,
    real_weights: np.ndarray,
    synthetic: pd.DataFrame,
    attributes: list[str],
    rng: np.random.Generator,
) -> float:
    """Classifier two-sample test.

    Real rows are resampled by weight so both sides are unweighted and equally sized, then a
    gradient-boosted classifier tries to tell them apart. AUC 0.5 means indistinguishable; the
    returned score is |AUC - 0.5| so that lower is better, consistent with the other metrics.
    """
    n = min(len(synthetic), 20_000)
    probabilities = real_weights / real_weights.sum()
    picks = rng.choice(len(real), size=n, p=probabilities)
    real_sample = real.iloc[picks][attributes].astype(str).reset_index(drop=True)
    synthetic_sample = synthetic[attributes].astype(str).iloc[:n].reset_index(drop=True)

    combined = pd.concat([real_sample, synthetic_sample], ignore_index=True)
    labels = np.r_[np.ones(len(real_sample)), np.zeros(len(synthetic_sample))]

    encoded = combined.apply(lambda column: column.astype("category").cat.codes)

    x_train, x_test, y_train, y_test = train_test_split(
        encoded.values, labels, test_size=0.3, random_state=0, stratify=labels
    )
    classifier = HistGradientBoostingClassifier(
        max_iter=120,
        categorical_features=list(range(encoded.shape[1])),
        random_state=0,
    )
    classifier.fit(x_train, y_train)
    scores = classifier.predict_proba(x_test)[:, 1]
    return abs(float(roc_auc_score(y_test, scores)) - 0.5)
