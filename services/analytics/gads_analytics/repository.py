from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from gads.models import (
    AccountAnalyticsSettings,
    AdAccount,
    Campaign,
    CampaignBudgetDaily,
    CampaignDaily,
    ChangeEvent,
    Keyword,
    KeywordDaily,
    SearchTermDaily,
    SyncRun,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gads_analytics.analysis import (
    Thresholds,
    budget_opportunities,
    campaign_drivers,
    compare_totals,
    detect_anomalies,
    evidence_claims,
    recommendations,
    thresholds_from_settings,
    top_changes,
    wasted_spend_candidates,
)
from gads_analytics.metrics import Totals, same_weekday_dates, window_for


def _f(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _opt(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _totals_from_row(row) -> Totals:
    return Totals(
        impressions=_f(row.impressions),
        clicks=_f(row.clicks),
        cost=_f(row.cost),
        conversions=_f(row.conversions),
        conversion_value=_f(row.conversion_value),
    )


def latest_data_date(session: Session, account_id: str) -> date | None:
    value = session.scalar(select(func.max(CampaignDaily.date)).where(CampaignDaily.account_id == account_id))
    return value


def resolve_as_of(session: Session, account_id: str, as_of: date | None) -> date:
    if as_of is not None:
        return as_of
    found = latest_data_date(session, account_id)
    if found is not None:
        return found
    return datetime.now(UTC).date() - timedelta(days=1)


def load_settings(session: Session, account_id: str) -> Thresholds:
    row = session.get(AccountAnalyticsSettings, account_id)
    return thresholds_from_settings(row)


def freshness(session: Session, account: AdAccount) -> dict:
    rows = session.execute(
        select(SyncRun.dataset, func.max(SyncRun.completed_at))
        .where(SyncRun.account_id == account.id, SyncRun.status == "completed")
        .group_by(SyncRun.dataset)
    ).all()
    datasets = {dataset: completed.isoformat() if completed else None for dataset, completed in rows}
    last_sync = account.last_successful_sync_at
    return {
        "last_successful_sync": last_sync.isoformat() if last_sync else None,
        "datasets": datasets,
    }


def _campaign_names(session: Session, account_id: str) -> dict[str, str]:
    rows = session.scalars(select(Campaign).where(Campaign.account_id == account_id)).all()
    return {row.id: row.name for row in rows}


def _rows_between(session: Session, account_id: str, start: date, end: date) -> list[CampaignDaily]:
    return list(
        session.scalars(
            select(CampaignDaily).where(
                CampaignDaily.account_id == account_id,
                CampaignDaily.date >= start,
                CampaignDaily.date <= end,
            )
        ).all()
    )


def _sum_rows(rows: list[CampaignDaily]) -> Totals:
    total = Totals()
    for row in rows:
        total = total.add(_totals_from_row(row))
    return total


def _by_campaign(rows: list[CampaignDaily]) -> dict[str, Totals]:
    grouped: dict[str, Totals] = defaultdict(Totals)
    for row in rows:
        grouped[row.campaign_id] = grouped[row.campaign_id].add(_totals_from_row(row))
    return dict(grouped)


def _filter_dates(rows: list[CampaignDaily], dates: set[date]) -> list[CampaignDaily]:
    return [row for row in rows if row.date in dates]


def comparison(session: Session, account_id: str, kind: str, as_of: date) -> dict:
    current_bounds, previous_bounds, normalization = window_for(kind, as_of)
    current_rows = _rows_between(session, account_id, *current_bounds)
    previous_rows = _rows_between(session, account_id, *previous_bounds)
    current = _sum_rows(current_rows)
    previous = _sum_rows(previous_rows)
    if normalization == "daily_average":
        days = (previous_bounds[1] - previous_bounds[0]).days + 1
        baseline = previous.scale(days)
    elif normalization == "same_weekday":
        weekday_dates = same_weekday_dates(as_of)
        dated = _filter_dates(previous_rows, set(weekday_dates))
        baseline = _sum_rows(dated).scale(len(weekday_dates))
        previous_bounds = (min(weekday_dates), max(weekday_dates))
    else:
        baseline = previous
    payload = compare_totals(current, baseline)
    payload["period"] = {
        "kind": kind,
        "normalization": normalization,
        "current_start": current_bounds[0].isoformat(),
        "current_end": current_bounds[1].isoformat(),
        "baseline_start": previous_bounds[0].isoformat(),
        "baseline_end": previous_bounds[1].isoformat(),
    }
    payload["current_rows"] = current_rows
    payload["previous_rows"] = previous_rows
    payload["current_totals"] = current
    payload["baseline_totals"] = baseline
    return payload


def _weighted_lost_is(session: Session, account_id: str, start: date, end: date) -> dict[str, float | None]:
    rows = session.scalars(
        select(CampaignBudgetDaily).where(
            CampaignBudgetDaily.account_id == account_id,
            CampaignBudgetDaily.date >= start,
            CampaignBudgetDaily.date <= end,
        )
    ).all()
    weighted: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        if row.lost_impression_share_budget is None:
            continue
        weight = float(row.impressions or 0) or 1.0
        weighted[row.campaign_id][0] += float(row.lost_impression_share_budget) * weight
        weighted[row.campaign_id][1] += weight
    return {key: (value[0] / value[1] if value[1] else None) for key, value in weighted.items()}


def campaign_performance(session: Session, account_id: str, start: date, end: date, limit: int, offset: int) -> dict:
    names = _campaign_names(session, account_id)
    grouped = _by_campaign(_rows_between(session, account_id, start, end))
    lost = _weighted_lost_is(session, account_id, start, end)
    rows = []
    for campaign_id, totals in grouped.items():
        metrics = totals.as_dict()
        metrics["campaign_id"] = campaign_id
        metrics["name"] = names.get(campaign_id, campaign_id)
        metrics["budget_lost_impression_share"] = lost.get(campaign_id)
        rows.append(metrics)
    rows.sort(key=lambda item: item["cost"], reverse=True)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "rows": rows[offset : offset + limit],
        "total": len(rows),
    }


def drivers_for(session: Session, account_id: str, kind: str, as_of: date, limit: int = 5) -> dict:
    compared = comparison(session, account_id, kind, as_of)
    names = _campaign_names(session, account_id)
    current = _by_campaign(compared["current_rows"])
    if compared["period"]["normalization"] == "same_weekday":
        previous_rows = _filter_dates(compared["previous_rows"], set(same_weekday_dates(as_of)))
    else:
        previous_rows = compared["previous_rows"]
    previous = _by_campaign(previous_rows)
    if compared["period"]["normalization"] in {"daily_average", "same_weekday"}:
        start = date.fromisoformat(compared["period"]["baseline_start"])
        end = date.fromisoformat(compared["period"]["baseline_end"])
        days = (end - start).days + 1 if compared["period"]["normalization"] == "daily_average" else max(len(same_weekday_dates(as_of)), 1)
        previous = {key: value.scale(days) for key, value in previous.items()}
    return campaign_drivers(current, previous, names, limit=limit)


def _entity_rows_from_search_terms(session: Session, account_id: str, start: date, end: date) -> list[dict]:
    names = _campaign_names(session, account_id)
    rows = session.scalars(
        select(SearchTermDaily).where(
            SearchTermDaily.account_id == account_id,
            SearchTermDaily.date >= start,
            SearchTermDaily.date <= end,
        )
    ).all()
    grouped: dict[tuple, Totals] = defaultdict(Totals)
    meta: dict[tuple, dict] = {}
    for row in rows:
        key = (row.search_term, row.campaign_id, row.match_type)
        grouped[key] = grouped[key].add(_totals_from_row(row))
        meta[key] = {
            "kind": "search_term",
            "id": row.id,
            "name": row.search_term,
            "campaign_id": row.campaign_id or None,
            "campaign_name": names.get(row.campaign_id, ""),
        }
    return [{**meta[key], "totals": totals} for key, totals in grouped.items()]


def _entity_rows_from_keywords(session: Session, account_id: str, start: date, end: date) -> list[dict]:
    names = {row.id: row.keyword_text for row in session.scalars(select(Keyword).where(Keyword.account_id == account_id))}
    campaign_names = _campaign_names(session, account_id)
    rows = session.scalars(
        select(KeywordDaily).where(
            KeywordDaily.account_id == account_id,
            KeywordDaily.date >= start,
            KeywordDaily.date <= end,
        )
    ).all()
    grouped: dict[str, Totals] = defaultdict(Totals)
    campaign_for: dict[str, str | None] = {}
    for row in rows:
        grouped[row.keyword_id] = grouped[row.keyword_id].add(_totals_from_row(row))
        campaign_for[row.keyword_id] = row.campaign_id
    return [
        {
            "kind": "keyword",
            "id": keyword_id,
            "name": names.get(keyword_id, keyword_id),
            "campaign_id": campaign_for.get(keyword_id),
            "campaign_name": campaign_names.get(campaign_for.get(keyword_id) or "", ""),
            "totals": totals,
        }
        for keyword_id, totals in grouped.items()
    ]


def search_term_report(session: Session, account_id: str, start: date, end: date, limit: int, offset: int) -> dict:
    entities = _entity_rows_from_search_terms(session, account_id, start, end)
    entities.sort(key=lambda item: item["totals"].cost, reverse=True)
    rows = []
    for item in entities[offset : offset + limit]:
        payload = item["totals"].as_dict()
        payload.update(
            {
                "search_term": item["name"],
                "campaign_id": item["campaign_id"],
                "campaign_name": item["campaign_name"],
            }
        )
        rows.append(payload)
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "rows": rows, "total": len(entities)}


def keyword_report(session: Session, account_id: str, start: date, end: date, limit: int, offset: int) -> dict:
    entities = _entity_rows_from_keywords(session, account_id, start, end)
    entities.sort(key=lambda item: item["totals"].cost, reverse=True)
    rows = []
    for item in entities[offset : offset + limit]:
        payload = item["totals"].as_dict()
        payload.update({"keyword_id": item["id"], "keyword_text": item["name"], "campaign_name": item["campaign_name"]})
        rows.append(payload)
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "rows": rows, "total": len(entities)}


def list_changes(session: Session, account_id: str, start: datetime, end: datetime, limit: int) -> list[dict]:
    rows = session.scalars(
        select(ChangeEvent)
        .where(
            ChangeEvent.account_id == account_id,
            ChangeEvent.event_timestamp >= start,
            ChangeEvent.event_timestamp <= end,
        )
        .order_by(ChangeEvent.event_timestamp.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "event_timestamp": row.event_timestamp.isoformat(),
            "resource_type": row.resource_type,
            "resource_changed_name": row.resource_changed_name,
            "change_type": row.change_type,
            "field_changed": row.field_changed,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "client_type": row.client_type,
            "user_email": row.user_email,
        }
        for row in rows
    ]


def build_report(session: Session, account: AdAccount, kind: str, as_of: date | None) -> dict:
    as_of = resolve_as_of(session, account.id, as_of)
    thresholds = load_settings(session, account.id)
    compared = comparison(session, account.id, kind, as_of)
    public_comparison = {
        "current": compared["current"],
        "baseline": compared["baseline"],
        "changes": compared["changes"],
        "period": compared["period"],
    }
    driver_payload = drivers_for(session, account.id, kind, as_of)
    names = _campaign_names(session, account.id)
    current_bounds = (
        date.fromisoformat(compared["period"]["current_start"]),
        date.fromisoformat(compared["period"]["current_end"]),
    )
    lost = _weighted_lost_is(session, account.id, *current_bounds)
    grouped = _by_campaign(compared["current_rows"])
    campaign_inputs = [
        {
            "campaign_id": campaign_id,
            "name": names.get(campaign_id, campaign_id),
            "totals": totals,
            "budget_lost_impression_share": lost.get(campaign_id),
        }
        for campaign_id, totals in grouped.items()
    ]
    anomalies = detect_anomalies(compared["current_totals"], compared["baseline_totals"], thresholds)
    for campaign in campaign_inputs:
        share = campaign["budget_lost_impression_share"]
        if share is not None and share >= thresholds.budget_lost_is_min:
            anomalies.append(
                {
                    "type": "budget_constraint",
                    "metric": "search_budget_lost_impression_share",
                    "current": share,
                    "baseline": None,
                    "percent_change": None,
                    "evidence": [f"{campaign['name']} lost {share:.1%} impression share to budget"],
                    "confidence": "high",
                    "campaign_id": campaign["campaign_id"],
                    "name": campaign["name"],
                }
            )
    account_cpa = compared["current_totals"].as_dict()["cost_per_conversion"]
    waste_rows = _entity_rows_from_search_terms(session, account.id, *current_bounds)
    waste_rows.extend(_entity_rows_from_keywords(session, account.id, *current_bounds))
    waste = wasted_spend_candidates(waste_rows, thresholds, account_cpa)
    budgets = budget_opportunities(campaign_inputs, thresholds, compared["current_totals"])
    start_dt = datetime.combine(current_bounds[0], datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(current_bounds[1], datetime.max.time(), tzinfo=UTC)
    changes = list_changes(session, account.id, start_dt, end_dt, limit=20)
    actions = recommendations(anomalies, waste, budgets, changes)
    return {
        "date": as_of.isoformat(),
        "data_freshness": freshness(session, account),
        "account": compared["current"],
        "comparison": public_comparison,
        "top_changes": top_changes(driver_payload),
        "anomalies": anomalies,
        "budget_opportunities": budgets,
        "wasted_spend": waste[:25],
        "recent_changes": changes,
        "campaign_drivers": driver_payload,
        "evidence": evidence_claims(public_comparison, driver_payload),
        "recommended_actions": actions,
    }


def account_summary(session: Session, account: AdAccount, start: date, end: date) -> dict:
    totals = _sum_rows(_rows_between(session, account.id, start, end))
    return {
        "account_id": account.id,
        "account_name": account.account_name,
        "customer_id": account.customer_id,
        "currency_code": account.currency_code,
        "timezone": account.timezone,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "metrics": totals.as_dict(),
        "data_freshness": freshness(session, account),
    }
