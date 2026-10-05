from datetime import date

from gads.models import AdAccount, Campaign, CampaignDaily, User, Workspace, WorkspaceMember
from gads.security import create_access_token
from gads_analytics.narrative import render_report
from gads_analytics.repository import build_report
from gads_ingestion.google_ads.fake import FakeGoogleAdsClient
from gads_ingestion.reconcile import reconcile_account
from gads_ingestion.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo
from gads_ingestion.sync import sync_campaign_daily, sync_campaigns, sync_search_terms
from sqlalchemy import func, select


def _account(session) -> AdAccount:
    user = User(email="owner@example.com", password_hash="x")
    session.add(user)
    session.flush()
    workspace = Workspace(name="Workspace")
    session.add(workspace)
    session.flush()
    session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    account = AdAccount(
        workspace_id=workspace.id,
        connection_id=_connection(session, workspace.id),
        customer_id="1234567890",
        account_name="Account",
        currency_code="EUR",
        timezone="Europe/Brussels",
    )
    session.add(account)
    session.flush()
    return account


def _connection(session, workspace_id: str) -> str:
    from gads.models import GoogleConnection

    connection = GoogleConnection(
        workspace_id=workspace_id,
        google_email="owner@example.com",
        refresh_token_encrypted="encrypted",
    )
    session.add(connection)
    session.flush()
    return connection.id


def test_sync_is_idempotent(session):
    account = _account(session)
    client = FakeGoogleAdsClient()
    sync_campaigns(session, account, client)
    sync_campaigns(session, account, client)
    sync_campaign_daily(session, account, client, date(2026, 9, 1), date(2026, 9, 1))
    sync_campaign_daily(session, account, client, date(2026, 9, 1), date(2026, 9, 1))
    sync_search_terms(session, account, client, date(2026, 9, 1), date(2026, 9, 1))
    sync_search_terms(session, account, client, date(2026, 9, 1), date(2026, 9, 1))
    session.flush()
    campaigns = session.scalar(select(func.count()).select_from(Campaign).where(Campaign.account_id == account.id))
    daily = session.scalar(select(func.count()).select_from(CampaignDaily).where(CampaignDaily.account_id == account.id))
    assert campaigns == 1
    assert daily == 1
    report = reconcile_account(session, account.id)
    assert report["ok"] is True


def test_daily_report_names_the_driver(session):
    payload = seed_demo(session, date(2026, 9, 15))
    account = session.get(AdAccount, payload["account_id"])
    report = build_report(session, account, "yesterday_vs_prev7_avg", date(2026, 9, 15))
    text = render_report(report)
    assert "Non-brand Search" in text
    assert "2026-09-15" in text
    assert "2026-09-08" in text
    assert report["data_freshness"]["last_successful_sync"]
    assert any(item["name"] == "Prospecting Exact" for item in report["budget_opportunities"])
    assert any(item["name"] == "free competitor alternative" for item in report["wasted_spend"])


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_and_workspace_isolation(client, session):
    created = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123", "workspace_name": "A"},
    )
    assert created.status_code == 201
    other = client.post(
        "/api/auth/register",
        json={"email": "b@example.com", "password": "password123", "workspace_name": "B"},
    )
    token_b = other.json()["access_token"]
    seeded = seed_demo(session, date(2026, 9, 15))
    session.commit()
    denied = client.get(
        "/api/reports/daily",
        params={"account_id": seeded["account_id"], "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code == 403
    owner = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    allowed = client.get(
        "/api/reports/daily",
        params={"account_id": seeded["account_id"], "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {create_access_token(owner.id)}"},
    )
    assert allowed.status_code == 200
    assert "Non-brand Search" in str(allowed.json()["campaign_drivers"])


def test_login_and_row_limit(client):
    client.post("/api/demo/seed")
    login = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert login.status_code == 200
    token = login.json()["access_token"]
    account_id = login.json()["user"]["workspaces"][0]["id"]
    accounts = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
    assert accounts.status_code == 200
    account_id = accounts.json()["accounts"][0]["id"]
    too_wide = client.get(
        "/api/campaigns",
        params={"account_id": account_id, "start_date": "2026-01-01", "end_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert too_wide.status_code == 400
    answer = client.post(
        "/api/ai/query",
        json={"account_id": account_id, "question": "What happened yesterday and what should I do today?", "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Demo seed uses yesterday relative to today when called without a date, so as_of may not be 2026-09-15.
    assert answer.status_code == 200
    assert answer.json()["model"] == "deterministic"
    assert "Evidence" in answer.json()["answer"] or "Recommended actions" in answer.json()["answer"]
