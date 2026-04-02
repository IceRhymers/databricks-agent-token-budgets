"""Pydantic schemas for session mapping."""

from __future__ import annotations

from pydantic import BaseModel


class SessionRegisterRequest(BaseModel):
    session_id: str


class SessionRegisterResponse(BaseModel):
    status: str
    user_email: str
