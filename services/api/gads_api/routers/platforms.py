from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from gads.config import get_settings
from gads.db import get_db
from gads.models import User, WorkspaceMember
from gads.platforms import PLATFORMS, platform_spec
from gads.security import create_oauth_state, decode_oauth_state
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_api.deps import current_user
from gads_api.platform_oauth import (
    PROVIDERS,
    authorization_url,
    exchange_code,
    save_platform_accounts,
)

router = APIRouter(prefix="/api", tags=["platforms"])


class ConnectRequest(BaseModel):
    workspace_id: str


def _configured(platform_id: str) -> bool:
    if platform_id == "google":
        settings = get_settings()
        return bool(settings.google_ads_client_id and settings.google_ads_client_secret and settings.google_ads_developer_token)
    spec = platform_spec(platform_id)
    settings = get_settings()
    return bool(spec.credential_env) and all(getattr(settings, env.lower(), "") for env in spec.credential_env)


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


@router.get("/platforms")
def list_platforms(_user: User = Depends(current_user)) -> dict:
    return {
        "platforms": [
            {
                "id": spec.id,
                "label": spec.label,
                "search_terms": spec.search_terms,
                "changes": spec.changes,
                "sync_ready": spec.sync_ready,
                "configured": _configured(spec.id),
            }
            for spec in PLATFORMS.values()
        ]
    }


@router.post("/platforms/{platform_id}/connect")
def connect_platform(
    platform_id: str,
    body: ConnectRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    spec = PLATFORMS.get(platform_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="That advertising platform is not supported.")
    if platform_id == "google":
        raise HTTPException(status_code=400, detail="Connect Google Ads from the Google sign-in button.")
    if platform_id not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"{spec.label} is not ready for sign-in yet.")
    missing = [name for name in spec.credential_env if not getattr(get_settings(), name.lower(), "")]
    if missing:
        names = ", ".join(missing)
        raise HTTPException(
            status_code=400,
            detail=f"{spec.label} needs {names} in the server environment before an account can be connected.",
        )
    _member(session, user.id, body.workspace_id)
    state = create_oauth_state(user.id, body.workspace_id, platform_id)
    return {"url": authorization_url(platform_id, state)}


@router.get("/platforms/{platform_id}/oauth/callback")
def platform_oauth_callback(platform_id: str, code: str = "", state: str = "", error: str = "", session: Session = Depends(get_db)):
    settings = get_settings()
    if platform_id not in PROVIDERS:
        return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
    if error or not code or not state:
        return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
    try:
        payload = decode_oauth_state(state)
    except Exception:
        return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
    if payload.get("platform") != platform_id:
        return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
    try:
        token_body = exchange_code(platform_id, code)
        if not token_body.get("access_token") and not token_body.get("refresh_token"):
            return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
        save_platform_accounts(session, payload["workspace_id"], platform_id, token_body)
    except Exception:
        return RedirectResponse(f"{settings.frontend_url}/configure?error=oauth")
    return RedirectResponse(f"{settings.frontend_url}/configure?connected=1&platform={platform_id}")
