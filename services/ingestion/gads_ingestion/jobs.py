from __future__ import annotations

import threading
import time
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

DATASET_LABELS = {
    "campaigns": "Campaigns",
    "ad_groups": "Ad groups",
    "keywords": "Keywords",
    "ads": "Ads",
    "campaign_daily": "Campaign performance",
    "ad_group_daily": "Ad group performance",
    "keyword_daily": "Keyword performance",
    "search_terms": "Search terms",
    "budgets": "Budgets",
    "change_events": "Change history",
}

_progress_lock = threading.Lock()
_progress: dict[str, dict] = {}


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
            try:
                session.commit()
            except Exception:
                session.rollback()
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


CHUNK_DAYS = 90


def date_window(mode: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    yesterday = today - timedelta(days=1)
    settings = get_settings()
    if mode == "initial":
        return yesterday - timedelta(days=settings.sync_initial_lookback_days - 1), yesterday
    if mode == "history":
        days = min(settings.sync_history_lookback_days, settings.ingest_max_days)
        return yesterday - timedelta(days=days - 1), yesterday
    if mode == "daily":
        return yesterday - timedelta(days=6), yesterday
    if mode == "weekly":
        return yesterday - timedelta(days=29), yesterday
    raise ValueError(f"Unknown sync mode: {mode}")


def iter_chunks(start: date, end: date, size: int = CHUNK_DAYS):
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=size - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _performance_windows(dataset: str, start: date, end: date):
    if dataset == "change_events":
        yield start, end
        return
    yield from iter_chunks(start, end)


def plan_sync_steps(start: date, end: date) -> list[dict]:
    steps = []
    for dataset in DATASETS:
        windows = _performance_windows(dataset, start, end) if dataset in PERFORMANCE else [(None, None)]
        for chunk_start, chunk_end in windows:
            label = DATASET_LABELS.get(dataset, dataset)
            if chunk_start is not None and chunk_end is not None:
                label = f"{label} · {chunk_start.isoformat()} to {chunk_end.isoformat()}"
            steps.append(
                {
                    "dataset": dataset,
                    "start": chunk_start.isoformat() if chunk_start else None,
                    "end": chunk_end.isoformat() if chunk_end else None,
                    "label": label,
                    "status": "pending",
                }
            )
    return steps


def _idle_progress() -> dict:
    return {"status": "idle", "total": 0, "completed": 0, "percent": 0, "label": None, "error": None}


def begin_sync_progress(account_id: str, steps: list[dict]) -> None:
    with _progress_lock:
        _progress[account_id] = {
            "status": "running",
            "total": len(steps),
            "completed": 0,
            "steps": steps,
            "error": None,
            "finished_at": None,
        }


def sync_progress(account_id: str) -> dict:
    with _progress_lock:
        state = _progress.get(account_id)
        if not state:
            return _idle_progress()
        finished_at = state.get("finished_at")
        if state["status"] == "completed" and finished_at is not None and time.time() - finished_at > 120:
            return _idle_progress()
        total = state["total"]
        completed = state["completed"]
        percent = 100 if state["status"] == "completed" else (0 if not total else int(100 * completed / total))
        label = None
        for step in state["steps"]:
            if step["status"] in {"running", "failed"}:
                label = step["label"]
                break
        if label is None and state["status"] == "completed":
            label = "Finished"
        error = state.get("error")
        return {
            "status": state["status"],
            "total": total,
            "completed": completed,
            "percent": percent,
            "label": label,
            "error": error[:500] if error else None,
        }


def _set_step_status(account_id: str, index: int, status: str, error: str | None = None) -> None:
    with _progress_lock:
        state = _progress.get(account_id)
        if not state or index >= len(state["steps"]):
            return
        state["steps"][index]["status"] = status
        state["completed"] = sum(1 for step in state["steps"] if step["status"] == "completed")
        if status == "failed":
            state["status"] = "failed"
            state["error"] = (error or "Sync failed")[:500]
            state["finished_at"] = time.time()
        elif state["completed"] == state["total"]:
            state["status"] = "completed"
            state["error"] = None
            state["finished_at"] = time.time()


def run_account_sync(account_id: str, mode: str = "initial", start: date | None = None, end: date | None = None) -> list[str]:
    if start is None or end is None:
        start, end = date_window(mode)
    steps = plan_sync_steps(start, end)
    with _progress_lock:
        existing = _progress.get(account_id)
        already_started = (
            existing is not None
            and existing["status"] == "running"
            and existing["completed"] == 0
            and existing["total"] == len(steps)
        )
    if not already_started:
        begin_sync_progress(account_id, steps)
    run_ids = []
    for index, step in enumerate(steps):
        _set_step_status(account_id, index, "running")
        try:
            if step["start"] and step["end"]:
                run_ids.append(JOBS[step["dataset"]](account_id, step["start"], step["end"]))
            else:
                run_ids.append(JOBS[step["dataset"]](account_id))
        except Exception as exc:
            _set_step_status(account_id, index, "failed", error=str(exc))
            raise
        _set_step_status(account_id, index, "completed")
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
            for chunk_start, chunk_end in _performance_windows(dataset, start, end):
                job = queue.enqueue(
                    JOBS[dataset],
                    account_id,
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                    retry=retry,
                    job_timeout=900,
                )
                job_ids.append(job.id)
        else:
            job = queue.enqueue(JOBS[dataset], account_id, retry=retry, job_timeout=900)
            job_ids.append(job.id)
    return job_ids
