from __future__ import annotations

from datetime import date, timedelta

import jwt
from fastapi import Depends, Header, HTTPException
from gads.config import get_settings
from gads.db import get_db
from gads.models import AdAccount, User, WorkspaceMember
from gads.security import decode_token
from sqlalchemy import select
from sqlalchemy.orm import Session


def current_user(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication is required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Authentication is required") from exc
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication is required")
    return user


def authorized_account(account_id: str, user: User, session: Session) -> AdAccount:
    account = session.get(AdAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account was not found")
    member = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == account.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if member is None:
        raise HTTPException(status_code=403, detail="You do not have access to this account")
    return account


def account_access(
    account_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> AdAccount:
    return authorized_account(account_id, user, session)


def resolve_dates(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    settings = get_settings()
    end = end_date or (date.today() - timedelta(days=1))
    start = start_date or (end - timedelta(days=6))
    if end < start:
        raise HTTPException(status_code=400, detail="end date is before start date")
    if (end - start).days + 1 > settings.tool_max_days:
        raise HTTPException(status_code=400, detail=f"Date range cannot exceed {settings.tool_max_days} days")
    return start, end


def bounded_limit(limit: int) -> int:
    settings = get_settings()
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be at least 1")
    return min(limit, settings.tool_max_rows)
