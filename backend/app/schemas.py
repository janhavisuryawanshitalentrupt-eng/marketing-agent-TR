"""Pydantic request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str = "admin"


class ForgotRequest(BaseModel):
    email: str


class ForgotResponse(BaseModel):
    message: str
    dev_code: str | None = None  # only populated in dev mode when email isn't configured


class ResetRequest(BaseModel):
    email: str
    code: str
    new_password: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None
    # Files the user attached in this turn: [{"name": str, "text": str}, ...]
    attachments: list[dict] | None = None


class ConversationOut(BaseModel):
    id: int
    title: str

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    assets: list = []

    class Config:
        from_attributes = True
