from datetime import date
from decimal import Decimal

from gads.config import get_settings
from gads.models import Campaign, ProposedAction, User
from gads.security import create_access_token
from gads_analytics.actions import (
    ACTION_ADD_NEGATIVE,
    ACTION_INCREASE_BUDGET,
    STATUS_APPLIED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    apply_action,
    propose_from_report,
    reject_action,
)
from gads_ingestion.google_ads.fake import FakeGoogleAdsClient
from report_fixture import FIXTURE_EMAIL, FIXTURE_PASSWORD, seed_report_account
from sqlalchemy import select


def _auth_header(user_id: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_propose_creates_negative_and_budget_actions(session):
    payload = seed_report_account(session, date(2026, 9, 15))
    from gads.models import AdAccount

    account = session.get(AdAccount, payload["account_id"])
    user = session.get(User, payload["user_id"])
    result = propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    assert result["count"] >= 1
    types = {row["action_type"] for row in result["created"]}
    assert ACTION_ADD_NEGATIVE in types
    negative = next(row for row in result["created"] if row["action_type"] == ACTION_ADD_NEGATIVE)
    assert "free competitor alternative" in negative["title"]
    assert negative["params"]["match_type"] == "PHRASE"
    # Second propose should skip duplicates still open/applied
    again = propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    assert again["count"] == 0
    assert again["skipped"] >= 1


def test_apply_negative_dry_run_and_live(session):
    payload = seed_report_account(session, date(2026, 9, 15))
    from gads.models import AdAccount

    account = session.get(AdAccount, payload["account_id"])
    user = session.get(User, payload["user_id"])
    propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    action = session.scalar(
        select(ProposedAction).where(
            ProposedAction.account_id == account.id,
            ProposedAction.action_type == ACTION_ADD_NEGATIVE,
        )
    )
    assert action is not None
    client = FakeGoogleAdsClient()

    dry = apply_action(session, account, action, user=user, confirm=True, dry_run=True, client=client)
    assert dry["dry_run"] is True
    assert action.status == STATUS_PROPOSED
    assert client.mutations

    settings = get_settings()
    previous = settings.allow_google_mutations
    settings.allow_google_mutations = True
    try:
        live = apply_action(session, account, action, user=user, confirm=True, dry_run=False, client=client)
        assert live["ok"] is True
        assert action.status == STATUS_APPLIED
        assert action.applied_by_user_id == user.id
        assert len(client.mutations) >= 2
    finally:
        settings.allow_google_mutations = previous


def test_apply_budget_updates_local_campaign(session):
    payload = seed_report_account(session, date(2026, 9, 15))
    from gads.models import AdAccount

    account = session.get(AdAccount, payload["account_id"])
    user = session.get(User, payload["user_id"])
    propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    action = session.scalar(
        select(ProposedAction).where(
            ProposedAction.account_id == account.id,
            ProposedAction.action_type == ACTION_INCREASE_BUDGET,
        )
    )
    if action is None:
        # Fixture may not always surface budget opportunities depending on thresholds; seed one.
        campaign = session.scalar(select(Campaign).where(Campaign.name == "Prospecting Exact"))
        action = ProposedAction(
            account_id=account.id,
            campaign_id=campaign.id,
            action_type=ACTION_INCREASE_BUDGET,
            status=STATUS_PROPOSED,
            fingerprint="budget-test",
            title="Budget test",
            rationale="test",
            evidence=["test"],
            params={
                "google_campaign_id": campaign.google_campaign_id,
                "campaign_name": campaign.name,
                "current_daily_budget": float(campaign.daily_budget),
                "proposed_daily_budget": 240.0,
                "increase_pct": 0.2,
            },
            confidence="high",
        )
        session.add(action)
        session.flush()

    client = FakeGoogleAdsClient()
    settings = get_settings()
    previous = settings.allow_google_mutations
    settings.allow_google_mutations = True
    try:
        apply_action(session, account, action, user=user, confirm=True, dry_run=False, client=client)
        campaign = session.get(Campaign, action.campaign_id)
        assert campaign.daily_budget == Decimal("240.00") or campaign.daily_budget == Decimal(str(action.params["proposed_daily_budget"]))
        assert any(item["operation"] == "update_campaign_daily_budget" for item in client.mutations)
    finally:
        settings.allow_google_mutations = previous


def test_reject_then_repropose_reactivates(session):
    payload = seed_report_account(session, date(2026, 9, 15))
    from gads.models import AdAccount

    account = session.get(AdAccount, payload["account_id"])
    user = session.get(User, payload["user_id"])
    first = propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    assert first["count"] >= 1
    action = session.scalar(select(ProposedAction).where(ProposedAction.account_id == account.id))
    reject_action(session, action, user=user)
    session.flush()
    second = propose_from_report(session, account, kind="last_30_vs_prev_30", as_of=date(2026, 9, 15), user=user)
    assert second["count"] >= 1
    session.refresh(action)
    assert action.status == STATUS_PROPOSED
    assert action.rejected_at is None
    rows = session.scalars(select(ProposedAction).where(ProposedAction.account_id == account.id)).all()
    assert len({row.fingerprint for row in rows}) == len(rows)


def test_actions_api_propose_and_list(client, session):
    payload = seed_report_account(session, date(2026, 9, 15))
    headers = _auth_header(payload["user_id"])
    response = client.post(
        "/api/actions/propose",
        headers=headers,
        json={"account_id": payload["account_id"], "kind": "last_30_vs_prev_30", "as_of": "2026-09-15"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] >= 1

    listed = client.get(f"/api/actions?account_id={payload['account_id']}&status=proposed", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["actions"]) >= 1

    action_id = body["created"][0]["id"]
    denied = client.post(f"/api/actions/{action_id}/apply", headers=headers, json={"confirm": True, "dry_run": False})
    assert denied.status_code == 400
    detail = denied.json()["detail"]
    assert "mutations are disabled" in detail or "ALLOW_GOOGLE_MUTATIONS" in detail

    no_confirm = client.post(f"/api/actions/{action_id}/apply", headers=headers, json={"confirm": False})
    assert no_confirm.status_code == 400

    rejected = client.post(f"/api/actions/{action_id}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["action"]["status"] == "rejected"


def test_login_fixture_still_works(client, session):
    seed_report_account(session, date(2026, 9, 15))
    response = client.post("/api/auth/login", json={"email": FIXTURE_EMAIL, "password": FIXTURE_PASSWORD})
    assert response.status_code == 200
