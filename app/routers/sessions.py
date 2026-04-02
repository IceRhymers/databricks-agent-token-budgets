"""Session mapping API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.auth import UserIdentity
from core.models import SessionMapping
from deps import get_current_user, get_db
from schemas.sessions import SessionRegisterRequest, SessionRegisterResponse

router = APIRouter(tags=["sessions"])


@router.post("/api/sessions/register", response_model=SessionRegisterResponse)
def register_session(
    body: SessionRegisterRequest,
    user: UserIdentity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = insert(SessionMapping).values(
        session_id=body.session_id,
        user_email=user.email,
    ).on_conflict_do_update(
        index_elements=["session_id"],
        set_={"user_email": user.email},
    )
    db.execute(stmt)
    db.commit()
    return SessionRegisterResponse(status="ok", user_email=user.email)
