from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config.settings import AppSettings
from src.persistence.models import Job, Study, UserUsageCounter
from src.services.exceptions import ProviderRunInFlightApiError, QuotaExceededApiError


METRIC_STUDY_CREATE: Final[str] = "study_create"
METRIC_SURVEY_UPLOAD: Final[str] = "survey_upload"
METRIC_PRODUCT_IMAGE_ANALYSIS: Final[str] = "product_image_analysis"
METRIC_SIMULATION_RUN: Final[str] = "simulation_run"
METRIC_STABILITY_CHECK: Final[str] = "stability_check"
METRIC_INTERVIEW_RUN: Final[str] = "interview_run"

PROVIDER_BACKED_METRICS: Final[set[str]] = {
    METRIC_SIMULATION_RUN,
    METRIC_STABILITY_CHECK,
    METRIC_INTERVIEW_RUN,
}
PROVIDER_BACKED_JOB_TYPES: Final[set[str]] = {
    "simulation_run",
    "simulation_stability",
    "interview_run",
}
IN_FLIGHT_JOB_STATUSES: Final[set[str]] = {"queued", "running"}


@dataclass(frozen=True)
class UsageQuotaSnapshot:
    metric_key: str
    bucket_date_utc: date
    count: int
    limit: int


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _quota_limit_for_metric(settings: AppSettings, metric_key: str) -> int:
    if metric_key == METRIC_STUDY_CREATE:
        return settings.daily_study_create_limit
    if metric_key in {METRIC_SURVEY_UPLOAD, METRIC_PRODUCT_IMAGE_ANALYSIS}:
        return settings.daily_upload_limit
    if metric_key in PROVIDER_BACKED_METRICS:
        return settings.daily_provider_run_limit
    raise ValueError(f"Unsupported usage metric: {metric_key}")


def _quota_exceeded_message(metric_key: str) -> str:
    if metric_key == METRIC_STUDY_CREATE:
        return "You’ve reached today’s study creation limit. Please try again tomorrow or contact support."
    if metric_key in {METRIC_SURVEY_UPLOAD, METRIC_PRODUCT_IMAGE_ANALYSIS}:
        return "You’ve reached today’s upload limit. Please try again tomorrow or contact support."
    return "You’ve reached today’s run limit. Please try again tomorrow or contact support."


def consume_daily_quota(
    session: Session,
    settings: AppSettings,
    *,
    owner_user_id: str,
    metric_key: str,
) -> UsageQuotaSnapshot:
    bucket = utc_today()
    limit = _quota_limit_for_metric(settings, metric_key)
    row = session.scalar(
        select(UserUsageCounter).where(
            UserUsageCounter.owner_user_id == owner_user_id,
            UserUsageCounter.metric_key == metric_key,
            UserUsageCounter.bucket_date_utc == bucket,
        )
    )
    current_count = row.count if row else 0
    if current_count >= limit:
        raise QuotaExceededApiError(
            _quota_exceeded_message(metric_key),
            details={
                "metric_key": metric_key,
                "bucket_date_utc": bucket.isoformat(),
                "limit": limit,
                "count": current_count,
            },
        )

    if row is None:
        row = UserUsageCounter(
            owner_user_id=owner_user_id,
            metric_key=metric_key,
            bucket_date_utc=bucket,
            count=1,
        )
    else:
        row.count += 1
        row.updated_at = datetime.now(timezone.utc)
    session.add(row)

    return UsageQuotaSnapshot(
        metric_key=metric_key,
        bucket_date_utc=bucket,
        count=row.count,
        limit=limit,
    )


def assert_no_in_flight_provider_job(
    session: Session,
    *,
    owner_user_id: str | None,
) -> None:
    if not owner_user_id:
        return

    existing_job = session.scalar(
        select(Job)
        .join(Study, Job.study_id == Study.id)
        .where(
            Study.owner_user_id == owner_user_id,
            Job.job_type.in_(sorted(PROVIDER_BACKED_JOB_TYPES)),
            Job.status.in_(sorted(IN_FLIGHT_JOB_STATUSES)),
        )
        .order_by(Job.queued_at.desc())
    )
    if existing_job is None:
        return

    raise ProviderRunInFlightApiError(
        "You already have a run in progress. Wait for it to finish before starting another.",
        details={
            "job_id": existing_job.public_id,
            "job_type": existing_job.job_type,
            "status": existing_job.status,
        },
    )
