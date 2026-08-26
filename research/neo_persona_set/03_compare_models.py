"""Stage 3 — compare persona-generation models on held-out ACS data.

Each model is fit on a weighted training split and scored on how well the population it generates
reproduces the joint structure of the held-out households. Every model runs over several seeds so
the winner is not seed luck.

Usage:
    python 03_compare_models.py [--seeds 5] [--sample-size 50000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import metrics, models, recode  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"

# The combination that decides whether someone can actually buy a $23k backyard studio.
PURCHASE_TRIPLE = ["income_bucket", "ownership", "home_type"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--sample-size", type=int, default=50_000)
    parser.add_argument("--test-fraction", type=float, default=0.25)
    args = parser.parse_args()

    frame = pd.read_parquet(OUT_DIR / "socal_frame.parquet")
    attributes = recode.MODEL_ATTRIBUTES
    print(f"Frame: {len(frame):,} households | attributes: {', '.join(attributes)}")

    rows: list[dict] = []

    for seed in range(args.seeds):
        rng = np.random.default_rng(seed)
        shuffled = rng.permutation(len(frame))
        cut = int(len(frame) * (1 - args.test_fraction))
        train = frame.iloc[shuffled[:cut]].reset_index(drop=True)
        test = frame.iloc[shuffled[cut:]].reset_index(drop=True)

        train_weights = train["WGTP"].values.astype(float)
        test_weights = test["WGTP"].values.astype(float)

        print(f"\n=== seed {seed} | train {len(train):,} | test {len(test):,} ===")

        for model_class in models.ALL_MODELS:
            model = model_class(attributes)
            started = time.perf_counter()
            model.fit(train[attributes], train_weights)
            fit_seconds = time.perf_counter() - started

            synthetic = model.sample(args.sample_size, np.random.default_rng(1000 + seed))

            mean_tvd, per_attribute = metrics.marginal_tvd(test, test_weights, synthetic, attributes)
            association, _ = metrics.pairwise_association_error(test, test_weights, synthetic, attributes)
            triple = metrics.joint_tvd(test, test_weights, synthetic, PURCHASE_TRIPLE)
            full_joint = metrics.joint_tvd(test, test_weights, synthetic, attributes)
            c2st = metrics.c2st_auc(test, test_weights, synthetic, attributes, np.random.default_rng(seed))
            loglik = model.log_likelihood(test[attributes], test_weights)

            rows.append(
                {
                    "model": model.name,
                    "seed": seed,
                    "marginal_tvd": mean_tvd,
                    "association_error": association,
                    "purchase_triple_tvd": triple,
                    "full_joint_tvd": full_joint,
                    "c2st_gap": c2st,
                    "held_out_loglik": loglik,
                    "fit_seconds": fit_seconds,
                    **{f"tvd__{k}": v for k, v in per_attribute.items()},
                }
            )
            print(
                f"  {model.name:<28} marginal={mean_tvd:.4f}  assoc={association:.4f}  "
                f"triple={triple:.4f}  joint={full_joint:.4f}  c2st={c2st:.4f}  ({fit_seconds:.1f}s)"
            )

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "model_comparison_runs.csv", index=False)

    score_columns = ["marginal_tvd", "association_error", "purchase_triple_tvd", "full_joint_tvd", "c2st_gap"]
    summary = results.groupby("model")[score_columns + ["held_out_loglik", "fit_seconds"]].agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    summary = summary.reset_index()

    # Composite rank over the lower-is-better fidelity metrics.
    for column in score_columns:
        summary[f"rank__{column}"] = summary[f"{column}_mean"].rank()
    rank_columns = [c for c in summary.columns if c.startswith("rank__")]
    summary["composite_rank"] = summary[rank_columns].mean(axis=1)
    summary = summary.sort_values("composite_rank").reset_index(drop=True)
    summary.to_csv(OUT_DIR / "model_comparison.csv", index=False)

    print("\n" + "=" * 100)
    print("RESULTS (mean over seeds; lower is better for every fidelity metric)")
    print("=" * 100)
    header = f"{'model':<28}{'marginal':>11}{'assoc':>11}{'triple':>11}{'joint':>11}{'c2st':>11}{'rank':>8}"
    print(header)
    print("-" * 100)
    for _, row in summary.iterrows():
        print(
            f"{row['model']:<28}"
            f"{row['marginal_tvd_mean']:>11.4f}"
            f"{row['association_error_mean']:>11.4f}"
            f"{row['purchase_triple_tvd_mean']:>11.4f}"
            f"{row['full_joint_tvd_mean']:>11.4f}"
            f"{row['c2st_gap_mean']:>11.4f}"
            f"{row['composite_rank']:>8.1f}"
        )

    # The bootstrap copies real rows, so it is the reference ceiling rather than a candidate to
    # deploy. The selected model is the best genuinely generative one.
    generative = summary[summary["model"] != "M1_weighted_bootstrap"]
    winner = generative.iloc[0]["model"]
    ceiling = summary[summary["model"] == "M1_weighted_bootstrap"]
    baseline = summary[summary["model"] == "M0_independent_marginals"].iloc[0]
    winner_row = summary[summary["model"] == winner].iloc[0]

    print("\nSelection")
    print(f"  reference ceiling (copies real rows) : {'M1_weighted_bootstrap' if len(ceiling) else 'n/a'}")
    print(f"  app's current method (baseline)      : M0_independent_marginals")
    print(f"  SELECTED generative model            : {winner}")
    improvement = (
        (baseline["association_error_mean"] - winner_row["association_error_mean"])
        / baseline["association_error_mean"]
        * 100
    )
    print(f"  association error vs baseline        : {improvement:.1f}% lower")

    selection = {
        "selected_model": winner,
        "reference_ceiling": "M1_weighted_bootstrap",
        "baseline": "M0_independent_marginals",
        "association_error_improvement_pct": float(improvement),
        "seeds": args.seeds,
        "sample_size": args.sample_size,
        "test_fraction": args.test_fraction,
        "metrics": {
            "marginal_tvd": "mean total variation distance across attribute marginals (lower better)",
            "association_error": "Frobenius distance between real and synthetic Cramer's V matrices (lower better)",
            "purchase_triple_tvd": f"TVD over {' x '.join(PURCHASE_TRIPLE)} (lower better)",
            "full_joint_tvd": "TVD over the full cross-tabulation of all attributes (lower better)",
            "c2st_gap": "|AUC - 0.5| for a classifier separating real from synthetic (lower better)",
            "held_out_loglik": "mean weighted log-likelihood of held-out rows (higher better; NaN if unsupported)",
        },
        "note": (
            "M1_weighted_bootstrap resamples real households, so it reproduces the joint "
            "distribution almost exactly. It is reported as the fidelity ceiling, not as a "
            "candidate; the deployable choice is the best generative model."
        ),
        "summary": json.loads(summary.to_json(orient="records")),
    }
    (OUT_DIR / "model_comparison.json").write_text(json.dumps(selection, indent=2))
    print(f"\nWrote model_comparison.csv, model_comparison_runs.csv, model_comparison.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
