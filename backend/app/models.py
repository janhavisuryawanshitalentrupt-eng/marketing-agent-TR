"""SQLAlchemy models — the 3-object spine (Brand, Campaign, Asset) plus support.

Generic JSON columns keep this portable between SQLite (dev) and PostgreSQL (prod).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AppSetting(Base):
    """Tiny key-value store for mutable runtime settings (e.g. the admin password override set via
    'forgot password', and the active password-reset code). Created by init_db()'s create_all — no
    migration needed. The config defaults still apply until a key is written here."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tagline: Mapped[str] = mapped_column(String(300), default="")
    voice: Mapped[str] = mapped_column(Text, default="")
    pillars: Mapped[list] = mapped_column(JSON, default=list)
    proof_points: Mapped[list] = mapped_column(JSON, default=list)
    services: Mapped[list] = mapped_column(JSON, default=list)
    brand_kit: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    kind: Mapped[str] = mapped_column(String(20), default="chat")  # chat | create | campaign
    # When this thread belongs to an (internal) campaign, link it so the folder restores its chat.
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    assets: Mapped[list] = mapped_column(JSON, default=list)  # asset ids/snapshots
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    name: Mapped[str] = mapped_column(String(300))
    # external = client-targeting (sector + prospects + calendar); internal = promote Talentrupt
    # itself via a chat-driven content folder.
    type: Mapped[str] = mapped_column(String(20), default="external")
    goal: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    pillar: Mapped[str] = mapped_column(String(200), default="")
    channels: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[str] = mapped_column(String(200), default="")
    kpis: Mapped[list] = mapped_column(JSON, default=list)
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="Asset.id"
    )
    prospects: Mapped[list["CampaignProspect"]] = relationship(
        cascade="all, delete-orphan", order_by="CampaignProspect.id"
    )
    items: Mapped[list["CampaignItem"]] = relationship(
        cascade="all, delete-orphan", order_by="CampaignItem.id"
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(40))  # post | image | deck | pdf | outreach
    title: Mapped[str] = mapped_column(String(400), default="")
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    campaign: Mapped["Campaign | None"] = relationship(back_populates="assets")


class Folder(Base):
    """A user-managed folder of employees — upload their REAL photos + name/role, then generate branded
    posts that feature them. Their actual photo is used; the face is never AI-generated."""
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    employees: Mapped[list["Employee"]] = relationship(
        cascade="all, delete-orphan", order_by="Employee.id"
    )


class Employee(Base):
    """One person in a Folder: their real photo + name + role. The ACTUAL photo is composited into
    generated posts; the face is never AI-generated."""
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200), default="")
    photo_path: Mapped[str] = mapped_column(String(600))  # on-disk path to the real COVER photo
    file_url: Mapped[str | None] = mapped_column(String(600), nullable=True)  # served URL for the thumbnail
    # Vision tags of the COVER photo (attire/expression/setting/framing/caption) so a feature can pick the
    # shot that best FITS the request. Filled lazily on first feature; the face is never altered.
    photo_analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Additional real photos of the SAME person (the cover above is photo #1). Multiple shots let a
    # feature pick the one that best fits the request; deleting the employee removes them all.
    photos: Mapped[list["EmployeePhoto"]] = relationship(
        cascade="all, delete-orphan", order_by="EmployeePhoto.id"
    )


class EmployeePhoto(Base):
    """An extra real photo attached to an Employee (beyond their cover `photo_path`). Same person,
    different shot — used to give featured-employee posts photo variety. Face is never AI-generated."""
    __tablename__ = "employee_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    photo_path: Mapped[str] = mapped_column(String(600))
    file_url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)  # vision tags (see Employee.photo_analysis)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CampaignItem(Base):
    """A planned content-calendar item within a future campaign."""
    __tablename__ = "campaign_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    scheduled_date: Mapped[datetime] = mapped_column(DateTime, default=_now)
    channel: Mapped[str] = mapped_column(String(60), default="")  # LinkedIn | Email | Instagram | Blog
    format: Mapped[str] = mapped_column(String(40), default="post")  # post | image | deck | pdf
    topic: Mapped[str] = mapped_column(String(400), default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="planned")  # planned | generated
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CampaignProspect(Base):
    """A scored target client matched to a specific campaign. 'Done' marks it handled
    and the campaign view pulls in a fresh replacement to keep the list full."""
    __tablename__ = "campaign_prospects"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    company: Mapped[str] = mapped_column(String(300), default="")
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # normalized discover() result
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    company: Mapped[str] = mapped_column(String(300))
    segment: Mapped[str] = mapped_column(String(200), default="")
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    signal: Mapped[str] = mapped_column(Text, default="")
    pain_point: Mapped[str] = mapped_column(Text, default="")
    service: Mapped[str] = mapped_column(String(300), default="")
    suggested_campaign: Mapped[str] = mapped_column(String(300), default="")
    why: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SourceFile(Base):
    """A file ingested from the Talentrupt source library (TR POSTS ZIP)."""
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = shared brand library (TR ZIP ingest); a role = a user's private upload.
    owner: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(700))
    folder: Mapped[str] = mapped_column(String(200), default="")
    file_type: Mapped[str] = mapped_column(String(20), default="")  # image | pdf
    size: Mapped[int] = mapped_column(Integer, default=0)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BrandChunk(Base):
    """A retrievable text chunk (image caption or PDF text) with its embedding."""
    __tablename__ = "brand_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_files.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="")  # image_caption | pdf_text
    text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CalendarTask(Base):
    """A scheduled follow-up / reminder (Business Dev outreach cadence)."""
    __tablename__ = "calendar_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # account that owns it
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(400))
    kind: Mapped[str] = mapped_column(String(40), default="followup")
    due_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input: Mapped[str] = mapped_column(Text, default="")
    tools_called: Mapped[list] = mapped_column(JSON, default=list)
    output: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
