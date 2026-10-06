from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from gads.db import get_db
from gads.models import ProposedAction, User
from gads_analytics.actions import (
    apply_action,
    list_actions,
    mark_action_failed,
    propose_from_report,
    reject_action,
)
from gads_ingestion.google_ads.mutations import GoogleMutationError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from gads_api.deps import authorized_account, current_user

router = APIRouter(prefix="/api", tags=["actions"])


class ProposeRequest(BaseModel):
    account_id: str
    kind: str = "last_30_vs_prev_30"
    as_of: date | None = None


class ApplyRequest(BaseModel):
    confirm: bool = False
    dry_run: bool = False


@router.post("/actions/propose")
def propose_actions(
    body: ProposeRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    account = authorized_account(body.account_id, user, session)
    try:
        result = propose_from_report(
            session,
            account,
            kind=body.kind,
            as_of=body.as_of,
            user=user,
        )
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/actions")
def get_actions(
    account_id: str,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    authorized_account(account_id, user, session)
    return {"actions": list_actions(session, account_id, status=status, limit=limit)}


@router.post("/actions/{action_id}/apply")
def apply_proposed_action(
    action_id: str,
    body: ApplyRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    action = session.get(ProposedAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action was not found")
    account = authorized_account(action.account_id, user, session)
    try:
        result = apply_action(
            session,
            account,
            action,
            user=user,
            confirm=body.confirm,
            dry_run=body.dry_run,
        )
        session.commit()
        return result
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GoogleMutationError as exc:
        session.rollback()
        failed = session.get(ProposedAction, action_id)
        if failed is not None:
            mark_action_failed(session, failed, str(exc))
            session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/actions/{action_id}/reject")
def reject_proposed_action(
    action_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_db),
) -> dict:
    action = session.get(ProposedAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action was not found")
    authorized_account(action.account_id, user, session)
    try:
        payload = reject_action(session, action, user=user)
        session.commit()
        return {"action": payload}
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
