"""Build grounding prior tables from US Census ACS PUMS microdata.

The persona generator samples grounded trait bundles from four prior tables. When
those tables are absent it silently degrades to a rule-based ("heuristic")
persona path, which produces demo-shaped respondents rather than grounded ones.
This script materializes the tables from ACS Public Use Microdata Sample (PUMS)
files so persona generation runs in `grounded_priors` mode.

PUMS is used rather than the ACS aggregate API because the sampler draws *joint*
trait rows (age x income, tenure x structure). PUMS microdata carries those true
joint distributions, and the bulk files need no API key.

Outputs (parquet, written to <legacy-root>/data/processed/priors/):
  age_income_priors.parquet          age_bucket x income_bucket
  ownership_home_type_priors.parquet ownership_group x home_type_group
  household_size_priors.parquet      household_size_bucket
  work_mode_hints.parquet            work_mode_hint

All tables carry survey-weighted `count` plus a normalized `share`.

Usage:
    python scripts/build_grounding_priors.py                # download + build
    python scripts/build_grounding_priors.py --cache-dir /tmp/pums
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterator

import pandas as pd

API_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEGACY_ROOT = API_ROOT / "legacy_runtime"

PUMS_BASE = "https://www2.census.gov/programs-surveys/acs/data/pums"
DEFAULT_YEAR = 2023
DEFAULT_DATASET = "1-Year"

# Only the columns the priors need; PUMS files carry ~250 columns each.
HOUSEHOLD_COLUMNS = ["TYPEHUGQ", "WGTP", "NP", "BLD", "TEN", "HHLDRAGEP", "HINCP", "ADJINC"]
PERSON_COLUMNS = ["PWGTP", "AGEP", "JWTRNS", "ESR"]

CHUNK_ROWS = 200_000


def _source_label(year: int, dataset: str) -> str:
    return f"acs_pums_{year}_{dataset.lower().replace('-', '')}"


def download(url: str, destination: Path) -> Path:
    """Download `url` to `destination`, reusing an existing complete file."""
    if destination.exists() and destination.stat().st_size > 0:
        print(f"  cached: {destination.name} ({destination.stat().st_size:,} bytes)")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    print(f"  downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)
    partial.replace(destination)
    print(f"  saved: {destination.name} ({destination.stat().st_size:,} bytes)")
    return destination


def iter_pums_chunks(zip_path: Path, columns: list[str]) -> Iterator[pd.DataFrame]:
    """Yield chunks from every PUMS CSV inside `zip_path`.

    National PUMS archives split records across several CSV members, so every
    `.csv` in the archive is read rather than just the first.
    """
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        if not csv_names:
            raise RuntimeError(f"No CSV members found inside {zip_path}")
        for name in csv_names:
            print(f"    reading {name}")
            with archive.open(name) as raw:
                buffer = io.TextIOWrapper(raw, encoding="latin-1")
                reader = pd.read_csv(
                    buffer,
                    usecols=lambda col: col in set(columns),
                    chunksize=CHUNK_ROWS,
                    low_memory=False,
                )
                for chunk in reader:
                    yield chunk


def age_bucket(age: float) -> str:
    if pd.isna(age):
        return "unknown"
    value = int(age)
    if value < 25:
        return "18_24"
    if value < 35:
        return "25_34"
    if value < 45:
        return "35_44"
    if value < 55:
        return "45_54"
    if value < 65:
        return "55_64"
    return "65_plus"


def income_bucket(income: float) -> str:
    if pd.isna(income):
        return "unknown"
    value = float(income)
    if value < 35_000:
        return "low"
    if value < 75_000:
        return "middle"
    if value < 150_000:
        return "upper_middle"
    return "high"


def ownership_group(tenure: float) -> str:
    """PUMS TEN: 1/2 owned (mortgage / free and clear), 3/4 rented or no-rent."""
    if pd.isna(tenure):
        return "unknown"
    value = int(tenure)
    if value in (1, 2):
        return "owner"
    if value in (3, 4):
        return "renter"
    return "unknown"


def home_type_group(structure: float) -> str:
    """PUMS BLD: 2/3 single-family, 4-9 multifamily, 1/10 mobile or other."""
    if pd.isna(structure):
        return "unknown"
    value = int(structure)
    if value in (2, 3):
        return "single_family_like"
    if value in (4, 5, 6, 7, 8, 9):
        return "multifamily_like"
    if value in (1, 10):
        return "mobile_or_other"
    return "unknown"


def household_size_bucket(size: float) -> str:
    if pd.isna(size):
        return "unknown"
    value = int(size)
    if value <= 0:
        return "unknown"
    if value == 1:
        return "1"
    if value == 2:
        return "2"
    if value <= 4:
        return "3_4"
    return "5_plus"


def work_mode_hint(commute: float, employment: float) -> str:
    """PUMS JWTRNS 11 is "worked from home"; 1-10/12 are commute modes.

    A blank JWTRNS means the person did not commute, which for an employed
    person still resolves to unknown rather than remote.
    """
    if not pd.isna(commute):
        value = int(commute)
        if value == 11:
            return "remote_friendly"
        if 1 <= value <= 12:
            return "commute_based"
    if pd.isna(employment):
        return "not_working_or_unknown"
    return "not_working_or_unknown"


def add_share(frame: pd.DataFrame) -> pd.DataFrame:
    total = float(frame["count"].sum())
    frame["share"] = frame["count"] / total if total > 0 else 0.0
    return frame


def build_household_priors(zip_path: Path, source: str) -> dict[str, pd.DataFrame]:
    """Aggregate weighted household counts for the three household-based priors."""
    age_income: dict[tuple[str, str], float] = {}
    ownership_home: dict[tuple[str, str], float] = {}
    sizes: dict[str, float] = {}

    total_rows = 0
    kept_rows = 0
    for chunk in iter_pums_chunks(zip_path, HOUSEHOLD_COLUMNS):
        total_rows += len(chunk)
        # Occupied housing units only: group quarters and vacant units carry no
        # household income, tenure, or size.
        occupied = chunk[(chunk["TYPEHUGQ"] == 1) & (chunk["WGTP"] > 0) & (chunk["NP"] > 0)]
        if occupied.empty:
            continue
        kept_rows += len(occupied)

        weights = occupied["WGTP"].astype(float)
        # ADJINC restates income in constant dollars for the survey year.
        adjusted_income = occupied["HINCP"].astype(float) * (occupied["ADJINC"].astype(float) / 1_000_000.0)

        ages = occupied["HHLDRAGEP"].map(age_bucket)
        incomes = adjusted_income.map(income_bucket)
        owners = occupied["TEN"].map(ownership_group)
        homes = occupied["BLD"].map(home_type_group)
        buckets = occupied["NP"].map(household_size_bucket)

        for key, weight in zip(zip(ages, incomes), weights):
            age_income[key] = age_income.get(key, 0.0) + weight
        for key, weight in zip(zip(owners, homes), weights):
            ownership_home[key] = ownership_home.get(key, 0.0) + weight
        for key, weight in zip(buckets, weights):
            sizes[key] = sizes.get(key, 0.0) + weight

    print(f"    households scanned={total_rows:,} occupied={kept_rows:,}")

    age_income_df = pd.DataFrame(
        [{"age_bucket": a, "income_bucket": i, "count": c} for (a, i), c in sorted(age_income.items())]
    )
    ownership_df = pd.DataFrame(
        [
            {"ownership_group": o, "home_type_group": h, "count": c}
            for (o, h), c in sorted(ownership_home.items())
        ]
    )
    size_df = pd.DataFrame(
        [{"household_size_bucket": b, "source": source, "count": c} for b, c in sorted(sizes.items())]
    )
    return {
        "age_income": add_share(age_income_df),
        "ownership_home_type": add_share(ownership_df),
        "household_size": add_share(size_df),
    }


def build_work_mode_prior(zip_path: Path) -> pd.DataFrame:
    """Aggregate weighted person counts by commute/remote status."""
    totals: dict[str, float] = {}
    scanned = 0
    for chunk in iter_pums_chunks(zip_path, PERSON_COLUMNS):
        scanned += len(chunk)
        working_age = chunk[(chunk["AGEP"] >= 16) & (chunk["PWGTP"] > 0)]
        if working_age.empty:
            continue
        hints = [
            work_mode_hint(commute, employment)
            for commute, employment in zip(working_age["JWTRNS"], working_age["ESR"])
        ]
        for hint, weight in zip(hints, working_age["PWGTP"].astype(float)):
            totals[hint] = totals.get(hint, 0.0) + weight
    print(f"    persons scanned={scanned:,}")
    frame = pd.DataFrame([{"work_mode_hint": k, "count": v} for k, v in sorted(totals.items())])
    return add_share(frame)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--dataset", default=DEFAULT_DATASET, choices=["1-Year", "5-Year"])
    parser.add_argument("--legacy-root", type=Path, default=DEFAULT_LEGACY_ROOT)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "synthetic-responder-pums",
        help="Where PUMS archives are downloaded and reused between runs.",
    )
    args = parser.parse_args()

    source = _source_label(args.year, args.dataset)
    base = f"{PUMS_BASE}/{args.year}/{args.dataset}"
    output_dir = args.legacy_root / "data" / "processed" / "priors"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building grounding priors from ACS PUMS {args.year} {args.dataset}")
    print("Downloading PUMS archives:")
    household_zip = download(f"{base}/csv_hus.zip", args.cache_dir / f"csv_hus_{args.year}.zip")
    person_zip = download(f"{base}/csv_pus.zip", args.cache_dir / f"csv_pus_{args.year}.zip")

    print("Aggregating household priors:")
    household_priors = build_household_priors(household_zip, source)
    print("Aggregating work-mode prior:")
    work_mode = build_work_mode_prior(person_zip)

    outputs = {
        "age_income_priors.parquet": household_priors["age_income"],
        "ownership_home_type_priors.parquet": household_priors["ownership_home_type"],
        "household_size_priors.parquet": household_priors["household_size"],
        "work_mode_hints.parquet": work_mode,
    }

    print(f"\nWriting priors to {output_dir}")
    for filename, frame in outputs.items():
        if frame.empty:
            print(f"  ERROR: {filename} is empty; refusing to write.", file=sys.stderr)
            return 1
        frame.attrs = {}
        frame.to_parquet(output_dir / filename, index=False)
        print(f"  {filename}: {len(frame)} rows")
        print(frame.to_string(index=False, max_rows=12))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
