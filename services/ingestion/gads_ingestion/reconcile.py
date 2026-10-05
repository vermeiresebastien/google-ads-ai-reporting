from __future__ import annotations

from gads.models import CampaignDaily, KeywordDaily
from gads_analytics.metrics import ratio
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _close(actual, expected, tolerance: float) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    return abs(float(actual) - float(expected)) <= tolerance


def reconcile_account(session: Session, account_id: str) -> dict:
    issues = []
    duplicate_campaigns = session.execute(
        select(CampaignDaily.account_id, CampaignDaily.date, CampaignDaily.campaign_id, func.count())
        .where(CampaignDaily.account_id == account_id)
        .group_by(CampaignDaily.account_id, CampaignDaily.date, CampaignDaily.campaign_id)
        .having(func.count() > 1)
    ).all()
    if duplicate_campaigns:
        issues.append({"check": "duplicate_campaign_daily", "count": len(duplicate_campaigns)})

    duplicate_keywords = session.execute(
        select(KeywordDaily.account_id, KeywordDaily.date, KeywordDaily.keyword_id, func.count())
        .where(KeywordDaily.account_id == account_id)
        .group_by(KeywordDaily.account_id, KeywordDaily.date, KeywordDaily.keyword_id)
        .having(func.count() > 1)
    ).all()
    if duplicate_keywords:
        issues.append({"check": "duplicate_keyword_daily", "count": len(duplicate_keywords)})

    rows = session.scalars(select(CampaignDaily).where(CampaignDaily.account_id == account_id)).all()
    for row in rows:
        if row.clicks > row.impressions:
            issues.append({"check": "clicks_exceed_impressions", "date": row.date.isoformat(), "campaign_id": row.campaign_id})
        expected_ctr = ratio(float(row.clicks), float(row.impressions))
        if not _close(row.ctr, expected_ctr, 0.0001):
            issues.append({"check": "ctr_mismatch", "date": row.date.isoformat(), "campaign_id": row.campaign_id})
        expected_roas = ratio(float(row.conversion_value), float(row.cost))
        if not _close(row.roas, expected_roas, 0.0001):
            issues.append({"check": "roas_mismatch", "date": row.date.isoformat(), "campaign_id": row.campaign_id})
    return {"account_id": account_id, "ok": not issues, "issues": issues}
