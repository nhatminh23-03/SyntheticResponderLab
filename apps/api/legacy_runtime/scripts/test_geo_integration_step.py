from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from backend.schemas import AudienceFilter
from backend.grounding.geography_context import build_geography_context_from_zip
from backend.simulation.persona_generator import (
    generate_persona_profiles_with_mode,
    get_last_persona_prior_notes,
)


def pct(counter: Counter, n: int) -> dict:
    return {k: round(v / n, 3) for k, v in counter.items()}


def dist(profiles, attr: str) -> dict:
    c = Counter(getattr(p, attr) for p in profiles)
    n = len(profiles)
    return dict(sorted(pct(c, n).items(), key=lambda kv: (-kv[1], str(kv[0]))))


def tv_distance(d1: dict, d2: dict) -> float:
    keys = set(d1) | set(d2)
    return round(0.5 * sum(abs(d1.get(k, 0.0) - d2.get(k, 0.0)) for k in keys), 3)


def run() -> None:
    sample_size = 80
    seed = 42

    results: dict = {}

    print("=== Test 1: ZIP 94103, no strong overrides ===")
    aud_94103 = AudienceFilter(state="California", zip_code="94103")
    geo_94103 = build_geography_context_from_zip("94103", prefer_local=True)
    profiles_geo, mode_geo = generate_persona_profiles_with_mode(
        audience_filter=aud_94103,
        sample_size=sample_size,
        use_grounded_priors=True,
        seed=seed,
        geography_context=geo_94103,
        use_geography_filtered_priors=True,
    )
    notes_geo = get_last_persona_prior_notes()
    narrowed_tables = [n.get("prior_table_name") for n in notes_geo if n.get("narrowed")]
    fallback_tables = [n.get("prior_table_name") for n in notes_geo if n.get("filter_level_used") == "global"]

    print("mode:", mode_geo)
    print(
        "geo_context:",
        {
            "zip": geo_94103.zip_code,
            "county": geo_94103.county_fips,
            "cbsa": geo_94103.cbsa_code,
            "puma": geo_94103.puma,
            "source": geo_94103.source,
        },
    )
    print("narrowed_tables:", narrowed_tables)
    print("global_fallback_tables:", fallback_tables)
    print("income_bucket_dist:", dist(profiles_geo, "income_bucket"))
    print("household_size_dist:", dist(profiles_geo, "household_size_bucket"))
    print("work_mode_dist:", dist(profiles_geo, "work_mode"))
    print()

    results["test1"] = {
        "mode": mode_geo,
        "geo_context": {
            "zip": geo_94103.zip_code,
            "county": geo_94103.county_fips,
            "cbsa": geo_94103.cbsa_code,
            "puma": geo_94103.puma,
            "source": geo_94103.source,
        },
        "narrowed_tables": narrowed_tables,
        "global_fallback_tables": fallback_tables,
        "income_bucket_dist": dist(profiles_geo, "income_bucket"),
        "household_size_dist": dist(profiles_geo, "household_size_bucket"),
        "work_mode_dist": dist(profiles_geo, "work_mode"),
    }

    print("=== Test 2: same ZIP 94103, with vs without geography-filtered priors ===")
    profiles_no_geo, mode_no_geo = generate_persona_profiles_with_mode(
        audience_filter=aud_94103,
        sample_size=sample_size,
        use_grounded_priors=True,
        seed=seed,
        geography_context=geo_94103,
        use_geography_filtered_priors=False,
    )
    notes_no_geo = get_last_persona_prior_notes()

    inc_geo = dist(profiles_geo, "income_bucket")
    inc_nogeo = dist(profiles_no_geo, "income_bucket")
    size_geo = dist(profiles_geo, "household_size_bucket")
    size_nogeo = dist(profiles_no_geo, "household_size_bucket")
    work_geo = dist(profiles_geo, "work_mode")
    work_nogeo = dist(profiles_no_geo, "work_mode")

    print("mode_with_geo:", mode_geo, "mode_without_geo:", mode_no_geo)
    print("notes_with_geo_narrowed:", len([n for n in notes_geo if n.get("narrowed")]))
    print("notes_without_geo_narrowed:", len([n for n in notes_no_geo if n.get("narrowed")]))
    print("income_tv_distance:", tv_distance(inc_geo, inc_nogeo))
    print("household_size_tv_distance:", tv_distance(size_geo, size_nogeo))
    print("work_mode_tv_distance:", tv_distance(work_geo, work_nogeo))
    print("income_with_geo:", inc_geo)
    print("income_without_geo:", inc_nogeo)
    print()

    results["test2"] = {
        "mode_with_geo": mode_geo,
        "mode_without_geo": mode_no_geo,
        "notes_with_geo_narrowed": len([n for n in notes_geo if n.get("narrowed")]),
        "notes_without_geo_narrowed": len([n for n in notes_no_geo if n.get("narrowed")]),
        "income_tv_distance": tv_distance(inc_geo, inc_nogeo),
        "household_size_tv_distance": tv_distance(size_geo, size_nogeo),
        "work_mode_tv_distance": tv_distance(work_geo, work_nogeo),
        "income_with_geo": inc_geo,
        "income_without_geo": inc_nogeo,
    }

    print("=== Test 3: different ZIP geography shift ===")
    candidate_zips = ["10001", "60601", "30301", "98101", "77002", "02108", "90012"]
    alt_zip = None
    alt_geo = None
    for z in candidate_zips:
        g = build_geography_context_from_zip(z, prefer_local=True)
        if g and g.puma and g.puma != geo_94103.puma:
            alt_zip = z
            alt_geo = g
            break

    if alt_zip is None:
        print("No alternate ZIP with distinct PUMA found in candidate list.")
        results["test3"] = {"status": "no_alt_zip_found"}
        _write_results(results)
        return

    aud_alt = AudienceFilter(zip_code=alt_zip)
    profiles_alt, mode_alt = generate_persona_profiles_with_mode(
        audience_filter=aud_alt,
        sample_size=sample_size,
        use_grounded_priors=True,
        seed=seed,
        geography_context=alt_geo,
        use_geography_filtered_priors=True,
    )
    notes_alt = get_last_persona_prior_notes()

    inc_alt = dist(profiles_alt, "income_bucket")
    size_alt = dist(profiles_alt, "household_size_bucket")
    work_alt = dist(profiles_alt, "work_mode")

    print("alt_zip:", alt_zip)
    print(
        "alt_geo:",
        {
            "zip": alt_geo.zip_code,
            "county": alt_geo.county_fips,
            "cbsa": alt_geo.cbsa_code,
            "puma": alt_geo.puma,
            "source": alt_geo.source,
        },
    )
    print("mode_alt:", mode_alt)
    print("alt_narrowed_tables:", [n.get("prior_table_name") for n in notes_alt if n.get("narrowed")])
    print("income_tv_distance_vs_94103:", tv_distance(inc_geo, inc_alt))
    print("household_size_tv_distance_vs_94103:", tv_distance(size_geo, size_alt))
    print("work_mode_tv_distance_vs_94103:", tv_distance(work_geo, work_alt))
    print("income_94103:", inc_geo)
    print("income_alt:", inc_alt)

    results["test3"] = {
        "alt_zip": alt_zip,
        "alt_geo": {
            "zip": alt_geo.zip_code,
            "county": alt_geo.county_fips,
            "cbsa": alt_geo.cbsa_code,
            "puma": alt_geo.puma,
            "source": alt_geo.source,
        },
        "mode_alt": mode_alt,
        "alt_narrowed_tables": [n.get("prior_table_name") for n in notes_alt if n.get("narrowed")],
        "income_tv_distance_vs_94103": tv_distance(inc_geo, inc_alt),
        "household_size_tv_distance_vs_94103": tv_distance(size_geo, size_alt),
        "work_mode_tv_distance_vs_94103": tv_distance(work_geo, work_alt),
        "income_94103": inc_geo,
        "income_alt": inc_alt,
    }

    _write_results(results)


def _write_results(results: dict) -> None:
    project_root = Path(__file__).resolve().parents[1]
    out_path = project_root / "data" / "processed" / "metadata" / "geo_integration_test_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("results_json:", out_path)


if __name__ == "__main__":
    run()
