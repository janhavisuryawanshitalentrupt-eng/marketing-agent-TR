"""Pydantic request/response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


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


# --- Magazine generator -------------------------------------------------------------------------
# All fields are LENGTH-CAPPED so a crafted request can't exhaust memory/CPU on the shared server (only ~6/4
# stats, ~24 spotlights and short strings are ever rendered anyway).
class MagStat(BaseModel):
    label: str = Field("", max_length=24)
    value: str = Field("", max_length=12)


class MagCover(BaseModel):
    employee_id: int | None = None
    headline: str = Field("", max_length=120)
    tagline: str = Field("", max_length=600)
    stats: list[MagStat] = Field(default_factory=list, max_length=6)


class MagSpotlight(BaseModel):
    employee_id: int | None = None
    office: str = Field("", max_length=60)
    blurb: str = Field("", max_length=600)
    stats: list[MagStat] = Field(default_factory=list, max_length=4)


class MagazineRequest(BaseModel):
    title: str = Field("Talentrupt Times", max_length=80)
    edition: str = Field("", max_length=60)
    theme: str = Field("", max_length=60)
    editorial: str = Field("", max_length=2500)
    cover: MagCover = Field(default_factory=MagCover)
    spotlights: list[MagSpotlight] = Field(default_factory=list, max_length=24)
