import io
import zipfile
from datetime import date

from gads.models import AdAccount, Campaign, CampaignDaily, User, Workspace, WorkspaceMember
from gads.security import create_access_token
from gads_analytics.narrative import render_report
from gads_analytics.repository import build_report
from gads_analytics.saved_reports import (
    list_saved_reports,
    rename_saved_report,
    save_report_summary,
)
from gads_ingestion.google_ads.fake import FakeGoogleAdsClient
from gads_ingestion.reconcile import reconcile_account
from gads_ingestion.sync import sync_campaign_daily, sync_campaigns, sync_search_terms
from report_fixture import FIXTURE_EMAIL, FIXTURE_PASSWORD, seed_report_account
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
    payload = seed_report_account(session, date(2026, 9, 15))
    account = session.get(AdAccount, payload["account_id"])
    report = build_report(session, account, "yesterday_vs_prev7_avg", date(2026, 9, 15))
    text = render_report(report)
    assert "Non-brand Search" in text
    assert "2026-09-15" in text
    assert "2026-09-08" in text
    assert report["data_freshness"]["last_successful_sync"]
    assert any(item["name"] == "Prospecting Exact" for item in report["budget_opportunities"])
    assert any(item["name"] == "free competitor alternative" for item in report["wasted_spend"])
    assert report["channels"]["channels"][0]["label"] == "Search"
    assert report["channels"]["brand"]["cost"] > 0
    assert report["channels"]["other"]["cost"] > report["channels"]["brand"]["cost"]
    assert [point["date"] for point in report["series"]] == ["2026-09-14", "2026-09-15"]
    week = build_report(session, account, "last_7_vs_prev_7", date(2026, 9, 15))
    assert week["series"][0]["date"] == "2026-09-09"
    assert week["series"][-1]["date"] == "2026-09-15"
    assert len(week["series"]) == 7
    assert len(report["recommended_actions"]) <= 3


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
    seeded = seed_report_account(session, date(2026, 9, 15))
    session.commit()
    denied = client.get(
        "/api/reports/daily",
        params={"account_id": seeded["account_id"], "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert denied.status_code == 403
    owner = session.scalar(select(User).where(User.email == FIXTURE_EMAIL))
    allowed = client.get(
        "/api/reports/daily",
        params={"account_id": seeded["account_id"], "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {create_access_token(owner.id)}"},
    )
    assert allowed.status_code == 200
    assert "Non-brand Search" in str(allowed.json()["campaign_drivers"])


def test_login_and_row_limit(client, session):
    seed_report_account(session, date(2026, 9, 15))
    session.commit()
    login = client.post("/api/auth/login", json={"email": FIXTURE_EMAIL, "password": FIXTURE_PASSWORD})
    assert login.status_code == 200
    token = login.json()["access_token"]
    accounts = client.get("/api/accounts", headers={"Authorization": f"Bearer {token}"})
    assert accounts.status_code == 200
    account_id = accounts.json()["accounts"][0]["id"]
    too_wide = client.get(
        "/api/campaigns",
        params={"account_id": account_id, "start_date": "2025-01-01", "end_date": "2026-09-01"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert too_wide.status_code == 400
    answer = client.post(
        "/api/ai/query",
        json={"account_id": account_id, "question": "What happened yesterday and what should I do today?", "as_of": "2026-09-15"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert answer.status_code == 200
    assert answer.json()["model"] == "deterministic"
    assert "Evidence" in answer.json()["answer"] or "Recommended actions" in answer.json()["answer"]


def test_asked_summaries_stay_beside_the_period_summary(session):
    seeded = seed_report_account(session, date(2026, 9, 15))
    session.commit()
    account = session.get(AdAccount, seeded["account_id"])
    report = build_report(session, account, "today_vs_yesterday", date(2026, 9, 15))
    save_report_summary(session, account.id, report, render_report(report))
    save_report_summary(session, account.id, report, "First council answer", "What changed yesterday?")
    save_report_summary(session, account.id, report, "First council answer, revised", "What changed yesterday?")
    save_report_summary(session, account.id, report, "Second council answer", "Why did spend rise?")
    rows = list_saved_reports(session, account.id)
    by_question = {row["question"]: row for row in rows}
    assert len(rows) == 3
    assert by_question[""]["kind"] == "today_vs_yesterday"
    assert by_question["What changed yesterday?"]["body"] == "First council answer, revised"
    assert by_question["What changed yesterday?"]["kind"].startswith("ask:")
    assert by_question["Why did spend rise?"]["body"] == "Second council answer"
    assert rename_saved_report(session, account.id, by_question[""]["id"], "Monday note")["title"] == "Monday note"
    save_report_summary(session, account.id, report, render_report(report))
    kept = list_saved_reports(session, account.id)
    assert next(row for row in kept if row["kind"] == "today_vs_yesterday")["title"] == "Monday note"


def test_daily_report_is_saved(client, session):
    seeded = seed_report_account(session, date(2026, 9, 15))
    session.commit()
    owner = session.scalar(select(User).where(User.email == FIXTURE_EMAIL))
    headers = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    params = {"account_id": seeded["account_id"], "as_of": "2026-09-15", "kind": "quarter_to_date_vs_prev"}
    first = client.get("/api/reports/daily", params=params, headers=headers)
    assert first.status_code == 200
    client.get("/api/reports/daily", params=params, headers=headers)
    saved = client.get("/api/reports/saved", params={"account_id": seeded["account_id"]}, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["as_of"]
    rows = saved.json()["reports"]
    assert len(rows) == 1
    assert rows[0]["kind"] == "quarter_to_date_vs_prev"
    assert "Executive summary" in rows[0]["body"]
    assert rows[0]["period_start"]
    assert rows[0]["period_end"]
    assert rows[0]["highlights"] == []
    assert rows[0]["title"] == ""
    renamed = client.patch(
        f"/api/reports/saved/{rows[0]['id']}",
        params={"account_id": seeded["account_id"]},
        headers=headers,
        json={"title": "Quarter review"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Quarter review"
    edited = client.patch(
        f"/api/reports/saved/{rows[0]['id']}",
        params={"account_id": seeded["account_id"]},
        headers=headers,
        json={"body": "Edited executive summary for the quarter."},
    )
    assert edited.status_code == 200
    assert edited.json()["body"] == "Edited executive summary for the quarter."
    painted = client.post(
        f"/api/reports/saved/{rows[0]['id']}/highlights",
        params={"account_id": seeded["account_id"]},
        headers=headers,
        json={"quote": "Executive summary", "color": "yellow", "note": "check this"},
    )
    assert painted.status_code == 200
    assert painted.json()["color"] == "yellow"
    rejected = client.post(
        f"/api/reports/saved/{rows[0]['id']}/highlights",
        params={"account_id": seeded["account_id"]},
        headers=headers,
        json={"quote": "not in this summary", "color": "orange"},
    )
    assert rejected.status_code == 400
    listed = client.get("/api/reports/saved", params={"account_id": seeded["account_id"]}, headers=headers)
    assert listed.json()["reports"][0]["highlights"][0]["note"] == "check this"
    cleared = client.delete(
        f"/api/reports/saved/{rows[0]['id']}/highlights/{painted.json()['id']}",
        params={"account_id": seeded["account_id"]},
        headers=headers,
    )
    assert cleared.status_code == 200
    exported = client.get(
        "/api/reports/saved/export",
        params={"account_id": seeded["account_id"], "start": "2026-09-15", "end": "2026-09-15"},
        headers=headers,
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    assert 'filename="2026-09-14 to 2026-09-15.zip"' in exported.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    names = archive.namelist()
    assert names == ["2026-09-14 to 2026-09-15.txt"]
    text = archive.read(names[0]).decode()
    assert text.startswith("Change from 2026-09-14 to 2026-09-15")
    assert "Executive summary" not in text
    removed = client.delete(
        f"/api/reports/saved/{rows[0]['id']}",
        params={"account_id": seeded["account_id"]},
        headers=headers,
    )
    assert removed.status_code == 200
    after = client.get("/api/reports/saved", params={"account_id": seeded["account_id"]}, headers=headers)
    assert after.json()["reports"] == []
    missing = client.delete(
        f"/api/reports/saved/{rows[0]['id']}",
        params={"account_id": seeded["account_id"]},
        headers=headers,
    )
    assert missing.status_code == 404
