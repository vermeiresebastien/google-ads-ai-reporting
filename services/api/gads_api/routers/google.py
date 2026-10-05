from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from gads.config import get_settings
from gads.db import get_db
from gads.models import AccountAnalyticsSettings, AdAccount, GoogleConnection, User, WorkspaceMember
from gads.security import create_oauth_state, decode_oauth_state, encrypt_secret
from gads_ingestion.discover import discover_accounts
from gads_ingestion.google_ads.client import build_client_for_refresh_token
from gads_ingestion.jobs import enqueue_account_sync
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_api.deps import authorized_account, current_user

router = APIRouter(prefix="/api", tags=["google"])
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"


class OAuthStartRequest(BaseModel):
    workspace_id: str


class SyncRequest(BaseModel):
    mode: str = "initial"
    start_date: str | None = None
    end_date: str | None = None


def _member(session: Session, user_id: str, workspace_id: str) -> WorkspaceMember:
    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
    )
    if member is None:
        raise HTTPException(status_code=403, detail="You do not have access to this workspace")
    return member


@router.post("/google/oauth/start")
def start_oauth(body: OAuthStartRequest, user: User = Depends(current_user), session: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.google_ads_client_id or not settings.google_ads_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth client is not configured")
    _member(session, user.id, body.workspace_id)
    state = create_oauth_state(user.id, body.workspace_id)
    query = urlencode(
        {
            "client_id": settings.google_ads_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/adwords https://www.googleapis.com/auth/userinfo.email",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return {"url": f"{GOOGLE_AUTH}?{query}"}


@router.get("/google/oauth/callback")
def oauth_callback(code: str, state: str, session: Session = Depends(get_db)):
    settings = get_settings()
    try:
        payload = decode_oauth_state(state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="OAuth state is invalid") from exc
    token_response = httpx.post(
        GOOGLE_TOKEN,
        data={
            "code": code,
            "client_id": settings.google_ads_client_id,
            "client_secret": settings.google_ads_client_secret,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if token_response.status_code >= 400:
        return RedirectResponse(f"{settings.frontend_url}/accounts?error=oauth")
    token_body = token_response.json()
    refresh_token = token_body.get("refresh_token")
    access_token = token_body.get("access_token")
    if not refresh_token:
        return RedirectResponse(f"{settings.frontend_url}/accounts?error=missing_refresh_token")
    email = ""
    if access_token:
        profile = httpx.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
        if profile.status_code < 400:
            email = profile.json().get("email") or ""
    workspace_id = payload["workspace_id"]
    connection = session.scalar(
        select(GoogleConnection).where(
            GoogleConnection.workspace_id == workspace_id,
            GoogleConnection.google_email == email,
        )
    )
    expires_at = None
    if token_body.get("expires_in"):
        expires_at = datetime.now(UTC) + timedelta(seconds=int(token_body["expires_in"]))
    if connection is None:
        connection = GoogleConnection(
            workspace_id=workspace_id,
            google_email=email,
            refresh_token_encrypted=encrypt_secret(refresh_token),
            access_token_encrypted=encrypt_secret(access_token) if access_token else None,
            access_token_expires_at=expires_at,
            status="active",
        )
        session.add(connection)
    else:
        connection.refresh_token_encrypted = encrypt_secret(refresh_token)
        connection.access_token_encrypted = encrypt_secret(access_token) if access_token else None
        connection.access_token_expires_at = expires_at
        connection.status = "active"
    session.flush()
    try:
        client = build_client_for_refresh_token(refresh_token, settings.google_ads_login_customer_id or None)
        discovered = discover_accounts(client)
    except Exception:
        connection.status = "error"
        session.commit()
        return RedirectResponse(f"{settings.frontend_url}/accounts?error=discovery")
    for item in discovered:
        account = session.scalar(
            select(AdAccount).where(
                AdAccount.workspace_id == workspace_id,
                AdAccount.customer_id == item["customer_id"],
            )
        )
        if account is None:
            account = AdAccount(workspace_id=workspace_id, connection_id=connection.id, customer_id=item["customer_id"])
            session.add(account)
            session.flush()
            session.add(AccountAnalyticsSettings(account_id=account.id))
        account.connection_id = connection.id
        account.manager_customer_id = item["manager_customer_id"]
        account.account_name = item["account_name"]
        account.currency_code = item["currency_code"]
        account.timezone = item["timezone"]
        account.status = item["status"]
    session.commit()
    return RedirectResponse(f"{settings.frontend_url}/accounts?connected=1")


@router.get("/accounts")
def list_accounts(user: User = Depends(current_user), session: Session = Depends(get_db)) -> dict:
    memberships = session.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).all()
    workspace_ids = [member.workspace_id for member in memberships]
    if not workspace_ids:
        return {"accounts": []}
    accounts = session.scalars(select(AdAccount).where(AdAccount.workspace_id.in_(workspace_ids))).all()
    return {
        "accounts": [
            {
                "id": account.id,
                "workspace_id": account.workspace_id,
                "customer_id": account.customer_id,
                "manager_customer_id": account.manager_customer_id,
                "account_name": account.account_name,
                "currency_code": account.currency_code,
                "timezone": account.timezone,
                "status": account.status,
                "last_successful_sync_at": account.last_successful_sync_at.isoformat() if account.last_successful_sync_at else None,
            }
            for account in accounts
        ]
    }


@router.post("/accounts/{account_id}/sync", status_code=202)
def sync_account(
    account_id: str,
    body: SyncRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    account = authorized_account(account_id, user, session)
    if body.mode not in {"initial", "daily", "weekly"} and not (body.start_date and body.end_date):
        raise HTTPException(status_code=400, detail="mode must be initial, daily, or weekly")
    start = None
    end = None
    if body.start_date and body.end_date:
        from datetime import date

        start = date.fromisoformat(body.start_date)
        end = date.fromisoformat(body.end_date)
    try:
        jobs = enqueue_account_sync(account.id, body.mode, start, end)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Redis is unavailable. Start Redis or run `python -m gads_ingestion.cli sync` for this account.",
        ) from exc
    return {"account_id": account.id, "jobs": jobs}
