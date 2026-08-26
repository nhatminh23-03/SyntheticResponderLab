"""Stage 1 — fetch live ACS PUMS microdata for California.

Downloads the person and housing PUMS files straight from www2.census.gov (public, no API key),
keeps only the columns the persona pipeline needs, and writes slim parquet files. Raw archives are
deleted afterwards unless --keep-raw is passed, because the extracted person CSV is several GB.

Usage:
    python 01_fetch_acs.py                 # 2024 5-Year (default, ~350 MB download)
    python 01_fetch_acs.py --vintage 1-year  # ~92 MB, faster iteration
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://www2.census.gov/programs-surveys/acs/data/pums"
STATE = "ca"
CHUNK_SIZE = 200_000

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
OUT_DIR = HERE / "out"

# Columns we need. Fetching only these keeps the parquet small and the read fast.
# ADJINC is mandatory: in a 5-Year file the income years differ, and HINCP must be multiplied by
# ADJINC (6 implied decimals) to land in constant dollars before any income comparison.
PERSON_COLUMNS = ["SERIALNO", "ST", "PUMA", "PWGTP", "AGEP", "JWTRNS", "RELSHIPP"]
HOUSING_COLUMNS = [
    "SERIALNO",
    "ST",
    "PUMA",
    "WGTP",
    "TEN",
    "BLD",
    "NP",
    "HINCP",
    "ADJINC",
    "OCPIP",
    "GRPIP",
]


def download(url: str, dest: Path) -> None:
    """Stream a file to disk, skipping if it is already present.

    Writes to a .part file and renames only on success, so an interrupted download can never be
    mistaken for a complete one on the next run.
    """
    if dest.exists():
        print(f"  already downloaded: {dest.name} ({dest.stat().st_size / 1048576:.0f} MB)")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        with partial.open("wb") as handle:
            for block in response.iter_content(chunk_size=1024 * 1024):
                handle.write(block)
                written += len(block)
                if total:
                    pct = 100 * written / total
                    print(f"\r    {written / 1048576:6.0f} / {total / 1048576:.0f} MB ({pct:4.1f}%)", end="")
        print()

    if total and written != total:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Short download for {dest.name}: got {written} of {total} bytes")

    partial.rename(dest)


def read_slim(zip_path: Path, wanted: list[str]) -> pd.DataFrame:
    """Read only `wanted` columns out of the CSVs inside a PUMS zip, in chunks."""
    frames: list[pd.DataFrame] = []

    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise RuntimeError(f"No CSV inside {zip_path.name}")

        for member in members:
            with archive.open(member) as raw:
                # Peek at the header so we only ask for columns that actually exist.
                head = pd.read_csv(io.BytesIO(raw.read(1024 * 64)), nrows=0)
            available = [c for c in wanted if c in head.columns]
            missing = sorted(set(wanted) - set(available))
            if missing:
                print(f"  WARNING: {member} is missing {missing}")

            with archive.open(member) as raw:
                for chunk in pd.read_csv(
                    raw,
                    usecols=available,
                    chunksize=CHUNK_SIZE,
                    low_memory=False,
                ):
                    frames.append(chunk)
            print(f"  read {member}")

    combined = pd.concat(frames, ignore_index=True)
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", choices=["1-year", "5-year"], default="5-year")
    parser.add_argument("--year", default="2024")
    parser.add_argument("--keep-raw", action="store_true", help="Do not delete the downloaded archives.")
    parser.add_argument(
        "--only",
        choices=["person", "housing"],
        help="Fetch just one file, so a re-run does not repeat the large person download.",
    )
    args = parser.parse_args()

    label = "5-Year" if args.vintage == "5-year" else "1-Year"
    base = f"{BASE_URL}/{args.year}/{label}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    targets = [
        ("person", f"csv_p{STATE}.zip", PERSON_COLUMNS),
        ("housing", f"csv_h{STATE}.zip", HOUSING_COLUMNS),
    ]
    if args.only:
        targets = [t for t in targets if t[0] == args.only]

    manifest: dict = {
        "source": "US Census Bureau ACS PUMS",
        "vintage": f"{args.year} {label}",
        "state": "California (ST=06)",
        "base_url": base,
        "files": [],
    }

    for kind, filename, columns in targets:
        print(f"\n[{kind}] {filename}")
        archive_path = RAW_DIR / filename
        download(f"{base}/{filename}", archive_path)

        frame = read_slim(archive_path, columns)
        out_path = OUT_DIR / f"acs_{kind}_slim.parquet"
        frame.to_parquet(out_path, index=False)
        print(f"  wrote {out_path.name}: {len(frame):,} rows x {len(frame.columns)} cols")

        manifest["files"].append(
            {
                "kind": kind,
                "source_file": filename,
                "url": f"{base}/{filename}",
                "rows": int(len(frame)),
                "columns": list(frame.columns),
                "output": out_path.name,
            }
        )

    # Merge with any existing manifest so a --only run does not drop the other file's record.
    manifest_path = OUT_DIR / "acs_download_manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        fetched_kinds = {entry["kind"] for entry in manifest["files"]}
        carried = [e for e in previous.get("files", []) if e["kind"] not in fetched_kinds]
        manifest["files"] = sorted(manifest["files"] + carried, key=lambda e: e["kind"])
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote manifest to {manifest_path}")

    if not args.keep_raw and RAW_DIR.exists():
        size = sum(f.stat().st_size for f in RAW_DIR.rglob("*") if f.is_file())
        shutil.rmtree(RAW_DIR)
        print(f"Removed raw archives ({size / 1048576:.0f} MB freed). Use --keep-raw to retain them.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
