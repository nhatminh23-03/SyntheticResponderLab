"""Backfill owner_user_id for existing studies prior to Clerk cutover.

This script assigns every study with a NULL owner_user_id (and, optionally,
any study whose owner matches a legacy placeholder) to a configured
bootstrap Clerk user id. It is intended to be run exactly once during the
auth cutover described in the README.

Usage (from the repository root):

    .venv/bin/python apps/api/scripts/backfill_study_owners.py \
        --owner user_2abc... \
        [--match-legacy] \
        [--dry-run]

The script loads backend settings from the standard environment, so the
DATABASE_URL used is the same one the API server connects to.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.config.settings import AppSettings, get_settings
from src.persistence.models import Study
from src.persistence.session import create_session_factory


LEGACY_PREFIX = "legacy:"


def _iter_affected_studies(
    session: Session,
    *,
    include_legacy: bool,
) -> Iterable[Study]:
    query = session.query(Study)
    if include_legacy:
        from sqlalchemy import or_

        query = query.filter(
            or_(
                Study.owner_user_id.is_(None),
                Study.owner_user_id.like(f"{LEGACY_PREFIX}%"),
            )
        )
    else:
        query = query.filter(Study.owner_user_id.is_(None))
    return query.all()


def backfill_owner(
    settings: AppSettings,
    *,
    owner_user_id: str,
    include_legacy: bool,
    dry_run: bool,
) -> int:
    session_factory = create_session_factory(settings)
    session = session_factory()
    try:
        affected = list(
            _iter_affected_studies(session, include_legacy=include_legacy)
        )
        count = len(affected)

        if dry_run:
            print(
                f"[dry-run] {count} study row(s) would be reassigned to {owner_user_id}."
            )
            for study in affected:
                print(
                    f"  study_id={study.public_id} "
                    f"current_owner={study.owner_user_id!r}"
                )
            return count

        if count == 0:
            print("No study rows needed backfilling.")
            return 0

        study_ids = [study.id for study in affected]
        session.execute(
            update(Study)
            .where(Study.id.in_(study_ids))
            .values(owner_user_id=owner_user_id)
        )
        session.commit()
        print(f"Reassigned {count} study row(s) to {owner_user_id}.")
        return count
    finally:
        session.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owner",
        required=True,
        help="Clerk user id (e.g. user_2abc...) to assign as the owner of unowned studies.",
    )
    parser.add_argument(
        "--match-legacy",
        action="store_true",
        help=(
            "Also reassign studies whose owner_user_id starts with the "
            "legacy: prefix that was used during the shared-password era."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify the database; print what would change.",
    )
    args = parser.parse_args(argv)

    owner = args.owner.strip()
    if not owner:
        parser.error("--owner cannot be empty.")

    settings = get_settings()
    backfill_owner(
        settings,
        owner_user_id=owner,
        include_legacy=args.match_legacy,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
