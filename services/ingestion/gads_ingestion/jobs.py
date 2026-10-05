from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from gads.config import get_settings
from gads.db import get_sessionmaker
from gads.logging import get_logger
from gads.models import AdAccount, SyncRun

from gads_ingestion import DATASETS
from gads_ingestion.google_ads.client import build_client
from gads_ingestion.sync import (
    run_tracked,
    sync_ad_group_daily,
    sync_ad_groups,
    sync_ads,
    sync_budgets,
    sync_campaign_daily,
    sync_campaigns,
    sync_change_events,
    sync_keyword_daily,
    sync_keywords,
    sync_search_terms,
)

logger = get_logger("gads.jobs")

PERFORMANCE = {
    "campaign_daily",
    "ad_group_daily",
    "keyword_daily",
    "search_terms",
    "budgets",
    "change_events",
}


def _execute(account_id: str, dataset: str, callback, start: date | None = None, end: date | None = None) -> str:
    session = get_sessionmaker()()
    try:
        account = session.get(AdAccount, account_id)
        if account is None:
            raise LookupError(f"Account {account_id} was not found")
        client = build_client(account)
        try:
            run = run_tracked(session, account, dataset, lambda: callback(session, account, client), start, end)
            session.commit()
            return run.id
        except Exception as exc:
            session.rollback()
            failed = SyncRun(
                account_id=account_id,
                dataset=dataset,
                status="failed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                start_date=start,
                end_date=end,
                error_message=str(exc)[:2000],
            )
            session.add(failed)
            session.commit()
            logger.error("sync_failed", account_id=account_id, dataset=dataset, error=failed.error_message)
            raise
    finally:
        session.close()


def sync_campaigns_job(account_id: str) -> str:
    return _execute(account_id, "campaigns", lambda session, account, client: sync_campaigns(session, account, client))


def sync_ad_groups_job(account_id: str) -> str:
    return _execute(account_id, "ad_groups", lambda session, account, client: sync_ad_groups(session, account, client))


def sync_keywords_job(account_id: str) -> str:
    return _execute(account_id, "keywords", lambda session, account, client: sync_keywords(session, account, client))


def sync_ads_job(account_id: str) -> str:
    return _execute(account_id, "ads", lambda session, account, client: sync_ads(session, account, client))


def sync_campaign_daily_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "campaign_daily",
        lambda session, account, client: sync_campaign_daily(session, account, client, start, end),
        start,
        end,
    )


def sync_ad_group_daily_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "ad_group_daily",
        lambda session, account, client: sync_ad_group_daily(session, account, client, start, end),
        start,
        end,
    )


def sync_keyword_daily_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "keyword_daily",
        lambda session, account, client: sync_keyword_daily(session, account, client, start, end),
        start,
        end,
    )


def sync_search_terms_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "search_terms",
        lambda session, account, client: sync_search_terms(session, account, client, start, end),
        start,
        end,
    )


def sync_budgets_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "budgets",
        lambda session, account, client: sync_budgets(session, account, client, start, end),
        start,
        end,
    )


def sync_change_events_job(account_id: str, start_date: str, end_date: str) -> str:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _execute(
        account_id,
        "change_events",
        lambda session, account, client: sync_change_events(session, account, client, start, end),
        start,
        end,
    )


JOBS = {
    "campaigns": sync_campaigns_job,
    "ad_groups": sync_ad_groups_job,
    "keywords": sync_keywords_job,
    "ads": sync_ads_job,
    "campaign_daily": sync_campaign_daily_job,
    "ad_group_daily": sync_ad_group_daily_job,
    "keyword_daily": sync_keyword_daily_job,
    "search_terms": sync_search_terms_job,
    "budgets": sync_budgets_job,
    "change_events": sync_change_events_job,
}


def date_window(mode: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    yesterday = today - timedelta(days=1)
    settings = get_settings()
    if mode == "initial":
        return yesterday - timedelta(days=settings.sync_initial_lookback_days - 1), yesterday
    if mode == "daily":
        return yesterday - timedelta(days=6), yesterday
    if mode == "weekly":
        return yesterday - timedelta(days=29), yesterday
    raise ValueError(f"Unknown sync mode: {mode}")


def run_account_sync(account_id: str, mode: str = "initial", start: date | None = None, end: date | None = None) -> list[str]:
    if start is None or end is None:
        start, end = date_window(mode)
    run_ids = []
    for dataset in DATASETS:
        if dataset in PERFORMANCE:
            run_ids.append(JOBS[dataset](account_id, start.isoformat(), end.isoformat()))
        else:
            run_ids.append(JOBS[dataset](account_id))
    return run_ids


def enqueue_account_sync(account_id: str, mode: str = "initial", start: date | None = None, end: date | None = None) -> list[str]:
    from redis import Redis
    from rq import Queue, Retry

    settings = get_settings()
    if start is None or end is None:
        start, end = date_window(mode)
    connection = Redis.from_url(settings.redis_url)
    queue = Queue("gads", connection=connection)
    retry = Retry(max=3, interval=[10, 30, 90])
    job_ids = []
    for dataset in DATASETS:
        if dataset in PERFORMANCE:
            job = queue.enqueue(
                JOBS[dataset],
                account_id,
                start.isoformat(),
                end.isoformat(),
                retry=retry,
                job_timeout=900,
            )
        else:
            job = queue.enqueue(JOBS[dataset], account_id, retry=retry, job_timeout=900)
        job_ids.append(job.id)
    return job_ids
