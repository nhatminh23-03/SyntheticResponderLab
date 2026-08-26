"""Persona-generation models for the bake-off.

Every model exposes the same interface:

    model = Model(attributes)
    model.fit(frame, weights)     # frame: DataFrame of categorical columns; weights: survey weights
    synthetic = model.sample(n, rng)
    loglik = model.log_likelihood(frame, weights)   # NaN when the model does not support it

All fitting is weight-aware. Ignoring WGTP would fit the sample rather than the population.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


class BaseModel:
    name = "base"
    supports_log_likelihood = False

    def __init__(self, attributes: list[str]):
        self.attributes = list(attributes)
        self.categories: dict[str, list] = {}

    def _record_categories(self, frame: pd.DataFrame) -> None:
        self.categories = {a: sorted(frame[a].astype(str).unique()) for a in self.attributes}

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "BaseModel":
        raise NotImplementedError

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        raise NotImplementedError

    def log_likelihood(self, frame: pd.DataFrame, weights: np.ndarray) -> float:
        return float("nan")


class IndependentMarginals(BaseModel):
    """Baseline: draw every attribute independently from its own weighted marginal.

    This reproduces what the app does today — `_sample_grounded_traits_with_rng` makes separate
    weighted draws per trait block, so the joint distribution is the product of the marginals.
    """

    name = "M0_independent_marginals"
    supports_log_likelihood = True

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "IndependentMarginals":
        self._record_categories(frame)
        self.marginals = {}
        total = weights.sum()
        for attribute in self.attributes:
            grouped = pd.Series(weights).groupby(frame[attribute].astype(str).values).sum()
            probabilities = (grouped / total).reindex(self.categories[attribute]).fillna(0.0)
            self.marginals[attribute] = probabilities.values / probabilities.values.sum()
        return self

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        data = {
            attribute: rng.choice(self.categories[attribute], size=n, p=self.marginals[attribute])
            for attribute in self.attributes
        }
        return pd.DataFrame(data)

    def log_likelihood(self, frame: pd.DataFrame, weights: np.ndarray) -> float:
        total = np.zeros(len(frame))
        for attribute in self.attributes:
            lookup = dict(zip(self.categories[attribute], self.marginals[attribute]))
            probabilities = frame[attribute].astype(str).map(lookup).fillna(1e-12).values
            total += np.log(np.clip(probabilities, 1e-12, None))
        return float(np.average(total, weights=weights))


class WeightedBootstrap(BaseModel):
    """Resample real households with probability proportional to WGTP.

    This is the joint-fidelity ceiling: it reproduces the real joint distribution exactly, because
    it copies real rows. It cannot invent combinations that never appear in the data.
    """

    name = "M1_weighted_bootstrap"

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "WeightedBootstrap":
        self._record_categories(frame)
        self.pool = frame[self.attributes].astype(str).reset_index(drop=True)
        self.probabilities = weights / weights.sum()
        return self

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        picks = rng.choice(len(self.pool), size=n, p=self.probabilities)
        return self.pool.iloc[picks].reset_index(drop=True)


class ChowLiuTree(BaseModel):
    """Chow-Liu tree Bayesian network over the categorical attributes.

    Keeps the strongest pairwise dependencies (a maximum spanning tree on mutual information) while
    staying cheap to fit and sample. A middle ground between full independence and the full joint.
    """

    name = "M2_chow_liu_bn"
    supports_log_likelihood = True

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "ChowLiuTree":
        self._record_categories(frame)
        data = frame[self.attributes].astype(str)
        total = weights.sum()
        k = len(self.attributes)

        joint: dict[tuple[int, int], pd.DataFrame] = {}
        mutual_information = np.zeros((k, k))

        for i in range(k):
            for j in range(i + 1, k):
                table = (
                    pd.DataFrame(
                        {
                            "a": data[self.attributes[i]].values,
                            "b": data[self.attributes[j]].values,
                            "w": weights,
                        }
                    )
                    .groupby(["a", "b"], observed=True)["w"]
                    .sum()
                    .unstack(fill_value=0.0)
                )
                probabilities = table.values / total
                row_marginal = probabilities.sum(axis=1, keepdims=True)
                col_marginal = probabilities.sum(axis=0, keepdims=True)
                with np.errstate(divide="ignore", invalid="ignore"):
                    term = probabilities * np.log(probabilities / (row_marginal * col_marginal))
                mutual_information[i, j] = mutual_information[j, i] = np.nansum(term)
                joint[(i, j)] = table

        # Maximum spanning tree via Prim's algorithm on the mutual-information matrix.
        in_tree = [0]
        edges: list[tuple[int, int]] = []
        while len(in_tree) < k:
            best = (-1.0, None, None)
            for a in in_tree:
                for b in range(k):
                    if b in in_tree:
                        continue
                    if mutual_information[a, b] > best[0]:
                        best = (mutual_information[a, b], a, b)
            _, parent, child = best
            edges.append((parent, child))
            in_tree.append(child)

        self.root = 0
        self.edges = edges
        self.children: dict[int, list[int]] = {}
        for parent, child in edges:
            self.children.setdefault(parent, []).append(child)

        # Root marginal.
        root_attribute = self.attributes[self.root]
        grouped = pd.Series(weights).groupby(data[root_attribute].values).sum()
        root_probabilities = (grouped / total).reindex(self.categories[root_attribute]).fillna(0.0)
        self.root_probabilities = root_probabilities.values / root_probabilities.values.sum()

        # Conditional tables P(child | parent).
        self.conditionals: dict[tuple[int, int], pd.DataFrame] = {}
        for parent, child in edges:
            key = (min(parent, child), max(parent, child))
            table = joint[key]
            if parent > child:
                table = table.T
            conditional = table.div(table.sum(axis=1).replace(0, np.nan), axis=0)
            conditional = conditional.reindex(
                index=self.categories[self.attributes[parent]],
                columns=self.categories[self.attributes[child]],
            )
            # A parent value unseen in training falls back to the child's marginal.
            child_marginal = table.sum(axis=0)
            child_marginal = child_marginal / child_marginal.sum()
            conditional = conditional.apply(
                lambda row: child_marginal.reindex(row.index).fillna(0.0) if row.isna().all() else row.fillna(0.0),
                axis=1,
            )
            self.conditionals[(parent, child)] = conditional
        return self

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        out: dict[str, np.ndarray] = {}
        root_attribute = self.attributes[self.root]
        out[root_attribute] = rng.choice(self.categories[root_attribute], size=n, p=self.root_probabilities)

        queue = list(self.children.get(self.root, []))
        parent_of = {child: parent for parent, child in self.edges}
        while queue:
            child = queue.pop(0)
            parent = parent_of[child]
            conditional = self.conditionals[(parent, child)]
            parent_values = out[self.attributes[parent]]
            child_values = np.empty(n, dtype=object)
            for parent_value, index in pd.Series(range(n)).groupby(parent_values).groups.items():
                probabilities = conditional.loc[parent_value].values.astype(float)
                probabilities = probabilities / probabilities.sum()
                idx = np.asarray(index)
                child_values[idx] = rng.choice(conditional.columns.values, size=len(idx), p=probabilities)
            out[self.attributes[child]] = child_values
            queue.extend(self.children.get(child, []))

        return pd.DataFrame({a: out[a] for a in self.attributes})

    def log_likelihood(self, frame: pd.DataFrame, weights: np.ndarray) -> float:
        data = frame[self.attributes].astype(str)
        lookup = dict(zip(self.categories[self.attributes[self.root]], self.root_probabilities))
        total = np.log(np.clip(data[self.attributes[self.root]].map(lookup).fillna(1e-12).values, 1e-12, None))
        for parent, child in self.edges:
            conditional = self.conditionals[(parent, child)]
            probabilities = np.array(
                [
                    conditional.at[p, c] if (p in conditional.index and c in conditional.columns) else 1e-12
                    for p, c in zip(data[self.attributes[parent]], data[self.attributes[child]])
                ],
                dtype=float,
            )
            total += np.log(np.clip(np.nan_to_num(probabilities, nan=1e-12), 1e-12, None))
        return float(np.average(total, weights=weights))


class GaussianCopula(BaseModel):
    """Gaussian copula over categorical attributes.

    Each category is mapped to an interval of the unit interval, pushed through the normal quantile
    function, correlated with a multivariate normal, then mapped back. Captures monotone pairwise
    association; it cannot represent non-monotone structure among nominal categories, which is a
    real limitation worth naming for attributes like home_type.
    """

    name = "M3_gaussian_copula"

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "GaussianCopula":
        self._record_categories(frame)
        data = frame[self.attributes].astype(str)
        total = weights.sum()

        self.bounds: dict[str, dict] = {}
        normals = np.zeros((len(data), len(self.attributes)))
        rng = np.random.default_rng(0)

        for column_index, attribute in enumerate(self.attributes):
            grouped = pd.Series(weights).groupby(data[attribute].values).sum()
            probabilities = (grouped / total).reindex(self.categories[attribute]).fillna(0.0)
            probabilities = probabilities / probabilities.sum()
            edges = np.concatenate([[0.0], np.cumsum(probabilities.values)])
            self.bounds[attribute] = {
                "categories": list(probabilities.index),
                "edges": edges,
            }
            lower = dict(zip(probabilities.index, edges[:-1]))
            upper = dict(zip(probabilities.index, edges[1:]))
            low = data[attribute].map(lower).values.astype(float)
            high = data[attribute].map(upper).values.astype(float)
            uniform = rng.uniform(low, high)
            uniform = np.clip(uniform, 1e-6, 1 - 1e-6)
            normals[:, column_index] = stats.norm.ppf(uniform)

        # Weighted correlation of the latent normals.
        mean = np.average(normals, axis=0, weights=weights)
        centered = normals - mean
        covariance = (centered * weights[:, None]).T @ centered / weights.sum()
        deviation = np.sqrt(np.diag(covariance))
        correlation = covariance / np.outer(deviation, deviation)
        # Nudge onto the PSD cone so the Cholesky factor exists.
        eigenvalues, eigenvectors = np.linalg.eigh(correlation)
        eigenvalues = np.clip(eigenvalues, 1e-6, None)
        correlation = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
        d = np.sqrt(np.diag(correlation))
        self.correlation = correlation / np.outer(d, d)
        return self

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        draws = rng.multivariate_normal(np.zeros(len(self.attributes)), self.correlation, size=n)
        uniform = stats.norm.cdf(draws)
        out: dict[str, np.ndarray] = {}
        for column_index, attribute in enumerate(self.attributes):
            spec = self.bounds[attribute]
            positions = np.searchsorted(spec["edges"], uniform[:, column_index], side="right") - 1
            positions = np.clip(positions, 0, len(spec["categories"]) - 1)
            out[attribute] = np.asarray(spec["categories"], dtype=object)[positions]
        return pd.DataFrame(out)


class LatentClass(BaseModel):
    """Latent class model: a mixture of independent categorical distributions, fit by EM.

    Within a class the attributes are independent; mixing the classes reproduces joint structure.
    This is the classical model for exactly this kind of survey data.
    """

    name = "M4_latent_class"
    supports_log_likelihood = True

    def __init__(self, attributes: list[str], n_classes: int = 8, max_iterations: int = 200, tolerance: float = 1e-6):
        super().__init__(attributes)
        self.n_classes = n_classes
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def _encode(self, frame: pd.DataFrame) -> list[np.ndarray]:
        codes = []
        for attribute in self.attributes:
            mapping = {c: i for i, c in enumerate(self.categories[attribute])}
            codes.append(frame[attribute].astype(str).map(mapping).fillna(-1).values.astype(int))
        return codes

    def fit(self, frame: pd.DataFrame, weights: np.ndarray) -> "LatentClass":
        self._record_categories(frame)
        codes = self._encode(frame)
        n = len(frame)
        rng = np.random.default_rng(0)

        self.class_probabilities = np.full(self.n_classes, 1.0 / self.n_classes)
        self.conditionals = []
        for attribute in self.attributes:
            size = len(self.categories[attribute])
            table = rng.dirichlet(np.ones(size), size=self.n_classes)
            self.conditionals.append(table)

        previous = -np.inf
        for _ in range(self.max_iterations):
            # E step: responsibilities in log space.
            log_responsibility = np.tile(np.log(self.class_probabilities), (n, 1))
            for attribute_index, code in enumerate(codes):
                table = np.clip(self.conditionals[attribute_index], 1e-12, None)
                log_responsibility += np.log(table[:, code]).T
            peak = log_responsibility.max(axis=1, keepdims=True)
            stabilized = np.exp(log_responsibility - peak)
            denominator = stabilized.sum(axis=1, keepdims=True)
            responsibility = stabilized / denominator
            loglik = float(np.average(np.log(denominator[:, 0]) + peak[:, 0], weights=weights))

            # M step, weighted by the survey weights.
            weighted = responsibility * weights[:, None]
            self.class_probabilities = weighted.sum(axis=0) / weighted.sum()
            for attribute_index, code in enumerate(codes):
                size = len(self.categories[self.attributes[attribute_index]])
                table = np.zeros((self.n_classes, size))
                for category_index in range(size):
                    mask = code == category_index
                    if mask.any():
                        table[:, category_index] = weighted[mask].sum(axis=0)
                table += 1e-9
                self.conditionals[attribute_index] = table / table.sum(axis=1, keepdims=True)

            if abs(loglik - previous) < self.tolerance:
                break
            previous = loglik

        return self

    def sample(self, n: int, rng: np.random.Generator) -> pd.DataFrame:
        classes = rng.choice(self.n_classes, size=n, p=self.class_probabilities)
        out: dict[str, np.ndarray] = {}
        for attribute_index, attribute in enumerate(self.attributes):
            values = np.empty(n, dtype=object)
            table = self.conditionals[attribute_index]
            options = np.asarray(self.categories[attribute], dtype=object)
            for class_index in range(self.n_classes):
                mask = classes == class_index
                count = int(mask.sum())
                if count:
                    values[mask] = rng.choice(options, size=count, p=table[class_index])
            out[attribute] = values
        return pd.DataFrame(out)

    def log_likelihood(self, frame: pd.DataFrame, weights: np.ndarray) -> float:
        codes = self._encode(frame)
        log_responsibility = np.tile(np.log(self.class_probabilities), (len(frame), 1))
        for attribute_index, code in enumerate(codes):
            table = np.clip(self.conditionals[attribute_index], 1e-12, None)
            safe = np.where(code >= 0, code, 0)
            contribution = np.log(table[:, safe]).T
            contribution[code < 0] = np.log(1e-12)
            log_responsibility += contribution
        peak = log_responsibility.max(axis=1, keepdims=True)
        total = np.log(np.exp(log_responsibility - peak).sum(axis=1)) + peak[:, 0]
        return float(np.average(total, weights=weights))


ALL_MODELS = [IndependentMarginals, WeightedBootstrap, ChowLiuTree, GaussianCopula, LatentClass]
