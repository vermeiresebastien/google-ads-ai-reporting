from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from gads.config import get_settings
from gads.models import AdAccount, Campaign, ProposedAction, User, utcnow
from gads_analytics.repository import build_report
from sqlalchemy import select
from sqlalchemy.orm import Session

ACTION_ADD_NEGATIVE = "add_negative_keyword"
ACTION_INCREASE_BUDGET = "increase_budget"
STATUS_PROPOSED = "proposed"
STATUS_APPLIED = "applied"
STATUS_REJECTED = "rejected"
STATUS_FAILED = "failed"
OPEN_STATUSES = (STATUS_PROPOSED, STATUS_FAILED)


def _fingerprint(*parts: str) -> str:
    raw = "|".join(part.strip().lower() for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def _match_type_for_term(text: str) -> str:
    tokens = [token for token in re.split(r"\s+", text.strip()) if token]
    return "EXACT" if len(tokens) <= 1 else "PHRASE"


def _money(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def action_public(row: ProposedAction) -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "campaign_id": row.campaign_id,
        "action_type": row.action_type,
        "status": row.status,
        "fingerprint": row.fingerprint,
        "title": row.title,
        "rationale": row.rationale,
        "evidence": row.evidence or [],
        "params": row.params or {},
        "confidence": row.confidence,
        "source_kind": row.source_kind,
        "source_as_of": row.source_as_of.isoformat() if row.source_as_of else None,
        "created_by_user_id": row.created_by_user_id,
        "applied_by_user_id": row.applied_by_user_id,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "google_response": row.google_response,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_actions(
    session: Session,
    account_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    query = select(ProposedAction).where(ProposedAction.account_id == account_id)
    if status:
        query = query.where(ProposedAction.status == status)
    query = query.order_by(ProposedAction.created_at.desc()).limit(limit)
    return [action_public(row) for row in session.scalars(query)]


def _actions_by_fingerprint(session: Session, account_id: str) -> dict[str, ProposedAction]:
    return {
        row.fingerprint: row
        for row in session.scalars(select(ProposedAction).where(ProposedAction.account_id == account_id))
    }


def _campaign_map(session: Session, account_id: str) -> dict[str, Campaign]:
    return {row.id: row for row in session.scalars(select(Campaign).where(Campaign.account_id == account_id))}


def _store_proposal(
    session: Session,
    known: dict[str, ProposedAction],
    *,
    fingerprint: str,
    account_id: str,
    campaign_id: str | None,
    action_type: str,
    title: str,
    rationale: str,
    evidence: list,
    params: dict,
    confidence: str,
    source_kind: str,
    source_as_of: date | None,
    user: User | None,
) -> ProposedAction | None:
    """Insert a new proposal, or reopen a rejected one. Skip open/applied duplicates."""
    existing = known.get(fingerprint)
    if existing is not None:
        if existing.status in OPEN_STATUSES + (STATUS_APPLIED,):
            return None
        existing.status = STATUS_PROPOSED
        existing.campaign_id = campaign_id
        existing.action_type = action_type
        existing.title = title
        existing.rationale = rationale
        existing.evidence = evidence
        existing.params = params
        existing.confidence = confidence
        existing.source_kind = source_kind
        existing.source_as_of = source_as_of
        existing.created_by_user_id = user.id if user else existing.created_by_user_id
        existing.applied_by_user_id = None
        existing.applied_at = None
        existing.rejected_at = None
        existing.google_response = None
        existing.error_message = None
        return existing

    row = ProposedAction(
        account_id=account_id,
        campaign_id=campaign_id,
        action_type=action_type,
        status=STATUS_PROPOSED,
        fingerprint=fingerprint,
        title=title,
        rationale=rationale,
        evidence=evidence,
        params=params,
        confidence=confidence,
        source_kind=source_kind,
        source_as_of=source_as_of,
        created_by_user_id=user.id if user else None,
    )
    session.add(row)
    known[fingerprint] = row
    return row


def propose_from_report(
    session: Session,
    account: AdAccount,
    *,
    kind: str = "last_30_vs_prev_30",
    as_of: date | None = None,
    user: User | None = None,
    max_negatives: int = 10,
    max_budgets: int = 5,
) -> dict:
    if (getattr(account, "platform", None) or "google") != "google":
        return {"created": [], "skipped": 0, "message": "Apply actions are only available for Google Ads accounts"}

    report = build_report(session, account, kind, as_of)
    campaigns = _campaign_map(session, account.id)
    known = _actions_by_fingerprint(session, account.id)
    created: list[ProposedAction] = []
    skipped = 0
    source_as_of = date.fromisoformat(report["date"]) if report.get("date") else as_of

    for item in (report.get("wasted_spend") or [])[:max_negatives]:
        if item.get("kind") == "keyword":
            skipped += 1
            continue
        campaign = campaigns.get(item.get("campaign_id") or "")
        if campaign is None:
            skipped += 1
            continue
        text = str(item.get("name") or "").strip()
        if not text:
            skipped += 1
            continue
        match_type = _match_type_for_term(text)
        fingerprint = _fingerprint(ACTION_ADD_NEGATIVE, account.id, campaign.id, text, match_type)
        metrics = item.get("metrics") or {}
        rationale = (
            f"Add “{text}” as a campaign negative ({match_type.lower()}). "
            f"It spent {float(metrics.get('cost') or 0):.2f} across {int(metrics.get('clicks') or 0)} clicks "
            f"and produced {float(metrics.get('conversions') or 0):.2f} conversions."
        )
        row = _store_proposal(
            session,
            known,
            fingerprint=fingerprint,
            account_id=account.id,
            campaign_id=campaign.id,
            action_type=ACTION_ADD_NEGATIVE,
            title=f"Negative: {text}",
            rationale=rationale,
            evidence=list(item.get("reasons") or []),
            params={
                "keyword_text": text,
                "match_type": match_type,
                "google_campaign_id": campaign.google_campaign_id,
                "campaign_name": campaign.name,
                "entity_kind": item.get("kind") or "search_term",
                "metrics": metrics,
            },
            confidence="medium",
            source_kind=kind,
            source_as_of=source_as_of,
            user=user,
        )
        if row is None:
            skipped += 1
        else:
            created.append(row)

    increase_pct = get_settings().budget_increase_pct
    for item in (report.get("budget_opportunities") or [])[:max_budgets]:
        campaign = campaigns.get(item.get("campaign_id") or "")
        if campaign is None or campaign.daily_budget is None:
            skipped += 1
            continue
        current = _money(campaign.daily_budget)
        proposed = _money(current * (1 + increase_pct))
        if proposed <= current:
            skipped += 1
            continue
        fingerprint = _fingerprint(ACTION_INCREASE_BUDGET, account.id, campaign.id, f"{proposed:.2f}")
        lost = item.get("budget_lost_impression_share")
        lost_text = f"{lost:.0%}" if isinstance(lost, (int, float)) else "unknown"
        rationale = (
            f"Raise daily budget for {campaign.name} from {current:.2f} to {proposed:.2f} "
            f"({increase_pct:.0%}). Budget is hiding {lost_text} of eligible impressions while efficiency stays near the account."
        )
        row = _store_proposal(
            session,
            known,
            fingerprint=fingerprint,
            account_id=account.id,
            campaign_id=campaign.id,
            action_type=ACTION_INCREASE_BUDGET,
            title=f"Budget +{increase_pct:.0%}: {campaign.name}",
            rationale=rationale,
            evidence=list(item.get("evidence") or []),
            params={
                "google_campaign_id": campaign.google_campaign_id,
                "campaign_name": campaign.name,
                "current_daily_budget": current,
                "proposed_daily_budget": proposed,
                "increase_pct": increase_pct,
                "budget_lost_impression_share": lost,
                "metrics": item.get("metrics") or {},
            },
            confidence=str(item.get("confidence") or "medium"),
            source_kind=kind,
            source_as_of=source_as_of,
            user=user,
        )
        if row is None:
            skipped += 1
        else:
            created.append(row)

    session.flush()
    return {
        "created": [action_public(row) for row in created],
        "skipped": skipped,
        "source_kind": kind,
        "source_as_of": source_as_of.isoformat() if source_as_of else None,
        "count": len(created),
    }


def reject_action(session: Session, action: ProposedAction, user: User | None = None) -> dict:
    if action.status not in OPEN_STATUSES:
        raise ValueError("Only proposed or failed actions can be rejected")
    action.status = STATUS_REJECTED
    action.rejected_at = utcnow()
    action.error_message = None
    if user is not None:
        action.applied_by_user_id = user.id
    session.flush()
    return action_public(action)


def apply_action(
    session: Session,
    account: AdAccount,
    action: ProposedAction,
    *,
    user: User,
    confirm: bool,
    dry_run: bool = False,
    client=None,
) -> dict:
    if not confirm:
        raise ValueError("confirm=true is required to apply an action")
    if action.status not in OPEN_STATUSES:
        raise ValueError("Only proposed or failed actions can be applied")
    if (getattr(account, "platform", None) or "google") != "google":
        raise ValueError("Apply actions are only available for Google Ads accounts")

    settings = get_settings()
    if not dry_run and not settings.allow_google_mutations:
        raise ValueError(
            "Live Google Ads mutations are disabled. Set ALLOW_GOOGLE_MUTATIONS=true, or use dry_run=true."
        )

    if client is None:
        from gads_ingestion.google_ads.client import build_client
        from gads_ingestion.google_ads.mutations import apply_google_action

        client = build_client(account)
        result = apply_google_action(client, account.customer_id, action, dry_run=dry_run)
    else:
        from gads_ingestion.google_ads.mutations import apply_google_action

        result = apply_google_action(client, account.customer_id, action, dry_run=dry_run)

    if dry_run:
        return {
            "dry_run": True,
            "ok": True,
            "action": action_public(action),
            "google": result,
        }

    action.google_response = result
    action.applied_by_user_id = user.id
    action.applied_at = utcnow()
    action.status = STATUS_APPLIED
    action.error_message = None

    if action.action_type == ACTION_INCREASE_BUDGET and action.campaign_id:
        campaign = session.get(Campaign, action.campaign_id)
        proposed = (action.params or {}).get("proposed_daily_budget")
        if campaign is not None and proposed is not None:
            campaign.daily_budget = Decimal(str(proposed))

    session.flush()
    return {"dry_run": False, "ok": True, "action": action_public(action), "google": result}


def mark_action_failed(session: Session, action: ProposedAction, message: str) -> dict:
    action.status = STATUS_FAILED
    action.error_message = message[:2000]
    session.flush()
    return action_public(action)
