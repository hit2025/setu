"""Relational model: Source, Passage, Claim, Evidence, Question, Snapshot, Receipt, Job, Audit.

Claims and evidence live in ordinary tables; dependencies are resolved by the readiness
engine, so no separate graph database is needed (matches the Round 1 plan).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32))  # departing | reviewer | engineer | coordinator
    title: Mapped[str] = mapped_column(String(160), default="")


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    project: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    departing_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    departure_date: Mapped[str] = mapped_column(String(10), default="")
    recipient_roles: Mapped[list] = mapped_column(JSON, default=lambda: ["engineer", "coordinator"])
    status: Mapped[str] = mapped_column(String(24), default="collecting")
    extractor_used: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    sources: Mapped[list["Source"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))  # markdown | text | csv | json | testimony
    label: Mapped[str] = mapped_column(String(24))  # public | team | engineering | finance | confidential
    raw_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))  # hash of canonical, masked text
    content: Mapped[str] = mapped_column(Text)  # canonical, masked text (the only text ever cited)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    masked: Mapped[dict] = mapped_column(JSON, default=dict)  # {kind: count}
    authored_at: Mapped[str] = mapped_column(String(32), default="")
    uploaded_by: Mapped[str] = mapped_column(String(32), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_reason: Mapped[str] = mapped_column(String(200), default="")

    case: Mapped[Case] = relationship(back_populates="sources")
    passages: Mapped[list["Passage"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Passage(Base):
    __tablename__ = "passages"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # <source_id>:p<idx>
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(String(200), default="")  # heading / author
    occurred_at: Mapped[str] = mapped_column(String(32), default="")

    source: Mapped[Source] = relationship(back_populates="passages")


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    ctype: Mapped[str] = mapped_column(String(16))  # decision owner task deadline dependency risk contact status
    subject: Mapped[str] = mapped_column(String(300))
    attribute: Mapped[str] = mapped_column(String(200))  # normalised key used for reconciliation
    value: Mapped[str] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(16), default="fact")  # decision | proposal | fact | testimony
    occurred_at: Mapped[str] = mapped_column(String(32), default="")
    origin: Mapped[str] = mapped_column(String(16), default="rules")  # rules | llm | manual | testimony
    support: Mapped[str] = mapped_column(String(16), default="supported")  # supported | weak | unsupported
    anchored: Mapped[bool] = mapped_column(Boolean, default=True)
    conflict_group: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    review_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending accepted edited rejected unresolved
    review_note: Mapped[str] = mapped_column(Text, default="")
    original_value: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str] = mapped_column(String(32), default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allowed_roles: Mapped[list] = mapped_column(JSON, default=list)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    question_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    passage_id: Mapped[str] = mapped_column(String(40))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    valid: Mapped[bool] = mapped_column(Boolean, default=True)

    claim: Mapped[Claim] = relationship(back_populates="evidence")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(200))  # dedupe key
    kind: Mapped[str] = mapped_column(String(24))  # conflict | missing_owner | owner_leaving | unknown_prereq | tacit
    prompt: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(String(16), default="departing")
    subject: Mapped[str] = mapped_column(String(300), default="")
    attribute: Mapped[str] = mapped_column(String(200), default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    related_claims: Mapped[list] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(24), default="team")
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | answered | closed
    answer: Mapped[str] = mapped_column(Text, default="")
    answer_value: Mapped[str] = mapped_column(String(300), default="")
    answered_by: Mapped[str] = mapped_column(String(32), default="")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str] = mapped_column(String(32))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    note: Mapped[str] = mapped_column(Text, default="")


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(32))
    view_hash: Mapped[str] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="reconstruct")
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued running done failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str | None] = mapped_column(String(12), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
