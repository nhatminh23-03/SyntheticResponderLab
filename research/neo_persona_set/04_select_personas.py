"""Stage 4 — select 15 survey-eligible personas, including 2-3 who would decline.

Refits the winning model on the whole frame, generates a synthetic population, screens it to the
survey's eligible population (owner + detached), attaches real continuous detail by donor sampling,
scores each persona's likely response from ACS fields, and picks a stratified set of 15.

Usage:
    python 04_select_personas.py [--pool 200000] [--rejectors 3]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import models, recode, rejection  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "out"

PERSONA_COUNT = 15
DONOR_KEYS = recode.MODEL_ATTRIBUTES


def build_model(name: str, attributes: list[str]):
    for model_class in models.ALL_MODELS:
        if model_class.name == name:
            return model_class(attributes)
    raise SystemExit(f"Unknown model in model_comparison.json: {name}")


def attach_donor_detail(synthetic: pd.DataFrame, frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Give each synthetic bundle real continuous values from a matching household.

    Hot-deck donor sampling: for a synthetic persona with a given attribute bundle, draw a real
    household sharing that bundle (with probability proportional to WGTP) and copy its income,
    cost burden, exact age, household size, and PUMA. Every number a reader sees therefore belongs
    to a real Census record rather than being invented.
    """
    donor_columns = ["adjusted_income", "owner_cost_burden", "AGEP", "NP", "puma", "SERIALNO"]
    frame = frame.reset_index(drop=True)
    frame["_key"] = frame[DONOR_KEYS].astype(str).agg("|".join, axis=1)
    synthetic = synthetic.reset_index(drop=True)
    synthetic["_key"] = synthetic[DONOR_KEYS].astype(str).agg("|".join, axis=1)

    groups = {key: group for key, group in frame.groupby("_key", observed=True)}
    picked: list[dict] = []
    unmatched = 0

    for key in synthetic["_key"]:
        group = groups.get(key)
        if group is None or group.empty:
            unmatched += 1
            picked.append({column: np.nan for column in donor_columns})
            continue
        weights = group["WGTP"].values.astype(float)
        index = rng.choice(len(group), p=weights / weights.sum())
        picked.append(group.iloc[index][donor_columns].to_dict())

    if unmatched:
        print(f"  note: {unmatched:,} synthetic bundles had no real donor and were dropped")

    detail = pd.DataFrame(picked)
    combined = pd.concat([synthetic.drop(columns=["_key"]), detail], axis=1)
    combined = combined[combined["SERIALNO"].notna()].reset_index(drop=True)
    combined["price_to_income"] = recode.price_to_income_ratio(combined["adjusted_income"])
    return combined


def derive_segment(row: pd.Series) -> str:
    """Name a segment from the attribute combination itself, not from a loop index."""
    remote = row["work_mode"] == "remote_friendly"
    big_household = row["household_size_bucket"] in {"3_4", "5_plus"}
    older = row["age_bucket"] in {"55_64", "65_plus"}
    wealthy = row["income_bucket"] in {"high", "upper_middle"}
    strained = pd.notna(row.get("price_to_income")) and row["price_to_income"] > 0.20

    if remote and wealthy:
        return "Remote Professional"
    if remote:
        return "Work-From-Home Striver"
    if big_household and wealthy:
        return "Family Space-Seeker"
    if big_household:
        return "Crowded-Household Pragmatist"
    if older and not big_household:
        return "Empty Nester"
    if strained:
        return "Budget-Constrained Owner"
    if wealthy:
        return "Established Homeowner"
    return "Value-Focused Owner"


def representative_pick(pool: pd.DataFrame, count: int, rng: np.random.Generator) -> pd.DataFrame:
    """Pick `count` rows that represent the pool, without repeating attribute bundles.

    The synthetic pool is already population-proportional — the model generates households at their
    real frequency — so rows are drawn uniformly FROM THE POOL rather than uniformly across strata.
    Sampling strata uniformly instead would treat a rare high-income remote-worker cell as equally
    likely as a common one and fill the set with outliers.

    Bundle uniqueness is a tie-breaker for readability, not a distributional target: a repeat is
    skipped while alternatives remain, and allowed once they run out.
    """
    if len(pool) <= count:
        return pool.copy()

    pool = pool.copy().reset_index(drop=True)
    pool["_bundle"] = pool[DONOR_KEYS].astype(str).agg("|".join, axis=1)

    order = rng.permutation(len(pool))
    chosen: list[int] = []
    seen_bundles: set[str] = set()

    for position in order:
        if len(chosen) >= count:
            break
        bundle = pool.at[position, "_bundle"]
        if bundle in seen_bundles:
            continue
        chosen.append(int(position))
        seen_bundles.add(bundle)

    # If distinct bundles ran out, top up with whatever remains.
    if len(chosen) < count:
        for position in order:
            if len(chosen) >= count:
                break
            if int(position) not in chosen:
                chosen.append(int(position))

    return pool.loc[chosen].drop(columns=["_bundle"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=int, default=200_000)
    parser.add_argument("--rejectors", type=int, default=3, help="How many of the 15 should decline (2 or 3).")
    parser.add_argument("--unsure", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    comparison = json.loads((OUT_DIR / "model_comparison.json").read_text())
    winner_name = comparison["selected_model"]
    print(f"Winning model from Stage 3: {winner_name}")

    frame = pd.read_parquet(OUT_DIR / "socal_frame.parquet")
    rng = np.random.default_rng(args.seed)

    print(f"\n[fit] refitting {winner_name} on the full frame ({len(frame):,} households)")
    model = build_model(winner_name, recode.MODEL_ATTRIBUTES)
    model.fit(frame[recode.MODEL_ATTRIBUTES], frame["WGTP"].values.astype(float))

    print(f"[sample] generating a synthetic population of {args.pool:,}")
    synthetic = model.sample(args.pool, rng)

    eligible = synthetic[
        synthetic["ownership"].eq("owner") & synthetic["home_type"].eq("detached")
    ].reset_index(drop=True)
    share = len(eligible) / len(synthetic)
    print(f"[screen] survey-eligible (owner + detached): {len(eligible):,} ({share:.1%})")

    print("[donor] attaching real income and cost-burden detail")
    eligible = attach_donor_detail(eligible, frame, rng)

    print("[score] labelling likely response from ACS fields")
    scored = rejection.score_frame(eligible)
    eligible = pd.concat([eligible, scored], axis=1)

    # Households with no positive income cannot be scored for a $23,000 purchase. They are a real
    # ACS category (business losses, no income), but they cannot be sensible personas here, so drop
    # them loudly rather than letting them default into 'accept'.
    unscorable = eligible["likely_response"].eq("not_scorable")
    if unscorable.any():
        print(
            f"  dropped {unscorable.sum():,} households ({unscorable.mean():.1%}) with zero or "
            "negative income — affordability is not assessable for them"
        )
        eligible = eligible[~unscorable].reset_index(drop=True)

    natural = eligible["likely_response"].value_counts(normalize=True)
    print("  natural rate among eligible households:")
    for label in ["accept", "unsure", "reject"]:
        print(f"    {label:<8} {natural.get(label, 0):.1%}")

    accepts = PERSONA_COUNT - args.rejectors - args.unsure
    targets = {"reject": args.rejectors, "unsure": args.unsure, "accept": accepts}
    print(f"\n[select] target mix: {targets}")

    chosen_parts = []
    for label, count in targets.items():
        subset = eligible[eligible["likely_response"].eq(label)]
        if len(subset) < count:
            raise SystemExit(
                f"Only {len(subset)} eligible households scored '{label}', need {count}. "
                "Increase --pool."
            )
        chosen_parts.append(representative_pick(subset, count, rng))

    personas = pd.concat(chosen_parts, ignore_index=True)
    personas["segment_label"] = personas.apply(derive_segment, axis=1)

    # Order so the workbook reads accept -> unsure -> reject.
    order = {"accept": 0, "unsure": 1, "reject": 2}
    personas = personas.sort_values(
        ["likely_response", "response_score"],
        key=lambda s: s.map(order) if s.name == "likely_response" else -s,
    ).reset_index(drop=True)
    personas.insert(0, "persona_id", [f"NEO_{i:02d}" for i in range(1, len(personas) + 1)])

    personas["annual_income_usd"] = personas["adjusted_income"].round(0)
    personas["price_pct_of_income"] = (personas["price_to_income"] * 100).round(1)
    personas["householder_age"] = personas["AGEP"].astype(int)
    personas["household_size"] = personas["NP"].astype(int)

    out_path = OUT_DIR / "persona_skeletons.json"
    payload = {
        "product": "Tahoe Mini by Neo Smart Living",
        "price_usd": recode.TAHOE_MINI_PRICE,
        "generated_by_model": winner_name,
        "seed": args.seed,
        "screen": "owner-occupied, detached single-family (outdoor-space proxy for survey screener S3)",
        "natural_response_rate_among_eligible": {k: float(v) for k, v in natural.items()},
        "selected_mix": targets,
        "scoring_rules": rejection.RULES,
        "thresholds": {"accept_at_or_above": rejection.ACCEPT_THRESHOLD, "reject_at_or_below": rejection.REJECT_THRESHOLD},
        "personas": json.loads(personas.to_json(orient="records")),
    }
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n{'id':<9}{'response':<9}{'score':>6}  {'segment':<30}{'income':>10}{'age':>5}{'hh':>4}  bundle")
    print("-" * 118)
    for _, row in personas.iterrows():
        bundle = f"{row['income_bucket']}/{row['work_mode']}/{row['household_size_bucket']}"
        print(
            f"{row['persona_id']:<9}{row['likely_response']:<9}{row['response_score']:>6.1f}  "
            f"{row['segment_label']:<30}${row['annual_income_usd']:>9,.0f}"
            f"{row['householder_age']:>5}{row['household_size']:>4}  {bundle}"
        )

    print(f"\nWrote {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
