from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from gads.config import get_settings
from gads.db import get_db
from gads.models import AccountAnalyticsSettings, AdAccount, Campaign, User
from gads_analytics.analysis import budget_opportunities, wasted_spend_candidates
from gads_analytics.ask import answer_question
from gads_analytics.metrics import assert_equal_length
from gads_analytics.repository import (
    _by_campaign,
    _campaign_names,
    _entity_rows_from_keywords,
    _entity_rows_from_search_terms,
    _rows_between,
    _sum_rows,
    _weighted_lost_is,
    account_summary,
    build_report,
    campaign_performance,
    comparison,
    drivers_for,
    freshness,
    keyword_report,
    list_changes,
    load_settings,
    resolve_as_of,
    search_term_report,
)
from gads_ingestion.seed import seed_demo
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_api.deps import (
    account_access,
    authorized_account,
    bounded_limit,
    current_user,
    resolve_dates,
)

router = APIRouter(prefix="/api", tags=["analytics"])


class QuestionRequest(BaseModel):
    account_id: str
    question: str = Field(min_length=3, max_length=2000)
    as_of: date | None = None


class SettingsUpdate(BaseModel):
    min_spend_for_waste: float | None = None
    spend_anomaly_pct: float | None = None
    cpa_anomaly_pct: float | None = None
    roas_anomaly_pct: float | None = None
    conversion_anomaly_pct: float | None = None
    cpc_anomaly_pct: float | None = None
    cvr_anomaly_pct: float | None = None
    zero_conversion_min_spend: float | None = None
    budget_lost_is_min: float | None = None
    min_clicks: int | None = None
    min_spend_for_anomaly: float | None = None


def _settings_payload(row: AccountAnalyticsSettings) -> dict:
    return {
        "account_id": row.account_id,
        "min_spend_for_waste": float(row.min_spend_for_waste),
        "spend_anomaly_pct": float(row.spend_anomaly_pct),
        "cpa_anomaly_pct": float(row.cpa_anomaly_pct),
        "roas_anomaly_pct": float(row.roas_anomaly_pct),
        "conversion_anomaly_pct": float(row.conversion_anomaly_pct),
        "cpc_anomaly_pct": float(row.cpc_anomaly_pct),
        "cvr_anomaly_pct": float(row.cvr_anomaly_pct),
        "zero_conversion_min_spend": float(row.zero_conversion_min_spend),
        "budget_lost_is_min": float(row.budget_lost_is_min),
        "min_clicks": row.min_clicks,
        "min_spend_for_anomaly": float(row.min_spend_for_anomaly),
    }


def _ensure_settings(session: Session, account_id: str) -> AccountAnalyticsSettings:
    row = session.get(AccountAnalyticsSettings, account_id)
    if row is None:
        row = AccountAnalyticsSettings(account_id=account_id)
        session.add(row)
        session.flush()
    return row


@router.get("/reports/daily")
def daily_report(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    as_of: date | None = None,
) -> dict:
    return build_report(session, account, "yesterday_vs_prev7_avg", as_of)


@router.get("/reports/weekly")
def weekly_report(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    as_of: date | None = None,
) -> dict:
    return build_report(session, account, "last_7_vs_prev_7", as_of)


@router.get("/compare")
def compare(
    kind: str,
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    as_of: date | None = None,
) -> dict:
    as_of = resolve_as_of(session, account.id, as_of)
    try:
        payload = comparison(session, account.id, kind, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "current": payload["current"],
        "baseline": payload["baseline"],
        "changes": payload["changes"],
        "period": payload["period"],
    }


@router.get("/compare/custom")
def compare_custom(
    current_start: date,
    current_end: date,
    previous_start: date,
    previous_end: date,
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
) -> dict:
    try:
        assert_equal_length(current_start, current_end, previous_start, previous_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resolve_dates(current_start, current_end)
    resolve_dates(previous_start, previous_end)
    current = _sum_rows(_rows_between(session, account.id, current_start, current_end))
    previous = _sum_rows(_rows_between(session, account.id, previous_start, previous_end))
    from gads_analytics.analysis import compare_totals

    payload = compare_totals(current, previous)
    payload["period"] = {
        "kind": "custom",
        "normalization": "totals",
        "current_start": current_start.isoformat(),
        "current_end": current_end.isoformat(),
        "baseline_start": previous_start.isoformat(),
        "baseline_end": previous_end.isoformat(),
    }
    return payload


@router.get("/summary")
def summary(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    return account_summary(session, account, start, end)


@router.get("/campaigns")
def campaigns(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    return campaign_performance(session, account.id, start, end, bounded_limit(limit), max(offset, 0))


@router.get("/campaigns/{campaign_id}")
def campaign_detail(
    campaign_id: str,
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
) -> dict:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.account_id != account.id:
        raise HTTPException(status_code=404, detail="Campaign was not found")
    return {
        "id": campaign.id,
        "google_campaign_id": campaign.google_campaign_id,
        "name": campaign.name,
        "status": campaign.status,
        "advertising_channel_type": campaign.advertising_channel_type,
        "campaign_type": campaign.campaign_type,
        "daily_budget": float(campaign.daily_budget) if campaign.daily_budget is not None else None,
    }


@router.get("/campaigns/{campaign_id}/performance")
def campaign_performance_route(
    campaign_id: str,
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.account_id != account.id:
        raise HTTPException(status_code=404, detail="Campaign was not found")
    start, end = resolve_dates(start_date, end_date)
    rows = [row for row in _rows_between(session, account.id, start, end) if row.campaign_id == campaign.id]
    from gads_analytics.repository import _totals_from_row

    daily = []
    for row in sorted(rows, key=lambda item: item.date):
        payload = _totals_from_row(row).as_dict()
        payload["date"] = row.date.isoformat()
        daily.append(payload)
    return {"campaign_id": campaign.id, "name": campaign.name, "rows": daily}


@router.get("/campaign-drivers")
def campaign_drivers_route(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    kind: str = "last_7_vs_prev_7",
    as_of: date | None = None,
) -> dict:
    as_of = resolve_as_of(session, account.id, as_of)
    try:
        return drivers_for(session, account.id, kind, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search-terms")
def search_terms(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    return search_term_report(session, account.id, start, end, bounded_limit(limit), max(offset, 0))


@router.get("/keywords")
def keywords(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    return keyword_report(session, account.id, start, end, bounded_limit(limit), max(offset, 0))


@router.get("/anomalies")
def anomalies(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    kind: str = "yesterday_vs_prev7_avg",
    as_of: date | None = None,
) -> dict:
    report = build_report(session, account, kind, as_of)
    return {"anomalies": report["anomalies"], "data_freshness": report["data_freshness"], "date": report["date"]}


@router.get("/budget-opportunities")
def budgets(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    thresholds = load_settings(session, account.id)
    names = _campaign_names(session, account.id)
    grouped = _by_campaign(_rows_between(session, account.id, start, end))
    lost = _weighted_lost_is(session, account.id, start, end)
    account_totals = _sum_rows(_rows_between(session, account.id, start, end))
    campaigns = [
        {
            "campaign_id": campaign_id,
            "name": names.get(campaign_id, campaign_id),
            "totals": totals,
            "budget_lost_impression_share": lost.get(campaign_id),
        }
        for campaign_id, totals in grouped.items()
    ]
    return {"rows": budget_opportunities(campaigns, thresholds, account_totals)}


@router.get("/wasted-spend")
def wasted(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    start, end = resolve_dates(start_date, end_date)
    thresholds = load_settings(session, account.id)
    totals = _sum_rows(_rows_between(session, account.id, start, end))
    rows = _entity_rows_from_search_terms(session, account.id, start, end)
    rows.extend(_entity_rows_from_keywords(session, account.id, start, end))
    return {"rows": wasted_spend_candidates(rows, thresholds, totals.as_dict()["cost_per_conversion"])}


@router.get("/changes")
def changes(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
) -> dict:
    from datetime import UTC, datetime

    start, end = resolve_dates(start_date, end_date)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(end, datetime.max.time(), tzinfo=UTC)
    return {"rows": list_changes(session, account.id, start_dt, end_dt, bounded_limit(limit))}


@router.get("/freshness")
def freshness_route(account: AdAccount = Depends(account_access), session: Session = Depends(get_db)) -> dict:
    return freshness(session, account)


@router.post("/ai/query")
def ai_query(
    body: QuestionRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    account = authorized_account(body.account_id, user, session)
    return answer_question(session, account, body.question, body.as_of)


@router.get("/accounts/{account_id}/settings")
def get_settings_route(account: AdAccount = Depends(account_access), session: Session = Depends(get_db)) -> dict:
    return _settings_payload(_ensure_settings(session, account.id))


@router.put("/accounts/{account_id}/settings")
def update_settings(
    body: SettingsUpdate,
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
) -> dict:
    row = _ensure_settings(session, account.id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(row, key, Decimal(str(value)) if key != "min_clicks" else int(value))
    session.commit()
    return _settings_payload(row)


@router.post("/demo/seed")
def demo_seed(session: Session = Depends(get_db)) -> dict:
    if not get_settings().enable_demo_seed:
        raise HTTPException(status_code=404, detail="Demo seed is disabled")
    payload = seed_demo(session)
    session.commit()
    return payload


@router.get("/sync-runs")
def sync_runs(
    account: AdAccount = Depends(account_access),
    session: Session = Depends(get_db),
    limit: int = Query(default=20),
) -> dict:
    from gads.models import SyncRun

    rows = session.scalars(
        select(SyncRun).where(SyncRun.account_id == account.id).order_by(SyncRun.started_at.desc()).limit(bounded_limit(limit))
    ).all()
    return {
        "rows": [
            {
                "id": row.id,
                "dataset": row.dataset,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "rows_fetched": row.rows_fetched,
                "rows_inserted": row.rows_inserted,
                "rows_updated": row.rows_updated,
                "error_message": row.error_message,
            }
            for row in rows
        ]
    }

