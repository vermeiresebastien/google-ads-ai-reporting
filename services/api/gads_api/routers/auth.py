from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from gads.db import get_db
from gads.models import User, Workspace, WorkspaceMember
from gads.security import create_access_token, hash_password, verify_password
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from gads_api.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


def _public_user(user: User, session: Session) -> dict:
    memberships = session.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).all()
    return {
        "id": user.id,
        "email": user.email,
        "workspaces": [
            {"id": member.workspace_id, "role": member.role}
            for member in memberships
        ],
    }


@router.post("/register", status_code=201)
def register(body: RegisterRequest, session: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    existing = session.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    session.add(user)
    session.flush()
    workspace = Workspace(name=body.workspace_name.strip())
    session.add(workspace)
    session.flush()
    session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.commit()
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _public_user(user, session),
    }


@router.post("/login")
def login(body: LoginRequest, session: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _public_user(user, session),
    }


@router.get("/me")
def me(user: User = Depends(current_user), session: Session = Depends(get_db)) -> dict:
    return _public_user(user, session)
