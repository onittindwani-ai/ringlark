"""Ringlark tables. They sit on the shared Base, so core tables and these migrate together."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sendora_core.db import Base, UTCDateTime, utcnow

DISPOSITIONS = ("booked", "interested_callback", "not_interested", "wrong_number", "do_not_call", "voicemail_left", "voicemail_no_message",
                "ivr_no_human", "hostile_ended", "transferred", "no_answer", "needs_review")
CALL_STATUSES = ("drafted", "blocked", "placed", "in_progress", "completed", "failed")
CAMPAIGN_STATUSES = ("draft", "running", "paused", "done")
TARGET_STATUSES = ("new", "queued", "contacted", "booked", "done", "suppressed")


class State(Base):
    __tablename__ = "rm_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Agent(Base):
    __tablename__ = "rm_agent"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(10), default="outbound")  # inbound or outbound
    company: Mapped[str] = mapped_column(String(120), default="")
    voice: Mapped[str] = mapped_column(String(80), default="")
    voice_source: Mapped[str] = mapped_column(String(20), default="builtin")  # builtin, cloned, elevenlabs, external
    greeting: Mapped[str] = mapped_column(Text, default="")
    transfer_number: Mapped[str] = mapped_column(String(32), default="")
    ab_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ab_share_b: Mapped[float] = mapped_column(Float, default=0.0)  # share of calls that use version B
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    versions: Mapped[list[PromptVersion]] = relationship(order_by="PromptVersion.version", back_populates="agent", cascade="all, delete-orphan")


class PromptVersion(Base):
    __tablename__ = "rm_prompt_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("rm_agent.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    agent: Mapped[Agent] = relationship(back_populates="versions")
    __table_args__ = (UniqueConstraint("agent_id", "version"),)


class Flow(Base):
    """The stages an agent walks through. Used in the editor and checked by the simulator."""
    __tablename__ = "rm_flow"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("rm_agent.id"))
    name: Mapped[str] = mapped_column(String(80))
    stages: Mapped[list] = mapped_column(JSON, default=list)  # [{"id","goal","exit_when"}]


class Number(Base):
    __tablename__ = "rm_number"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    e164: Mapped[str] = mapped_column(String(32), unique=True)
    label: Mapped[str] = mapped_column(String(80), default="")
    direction: Mapped[str] = mapped_column(String(10), default="both")
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("rm_agent.id"), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="US")
    checklist: Mapped[dict] = mapped_column(JSON, default=dict)  # name of step -> true or false (client's own registrations)


class Campaign(Base):
    __tablename__ = "rm_campaign"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    agent_id: Mapped[int] = mapped_column(ForeignKey("rm_agent.id"))
    number_id: Mapped[int | None] = mapped_column(ForeignKey("rm_number.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)
    window_start_hour: Mapped[int] = mapped_column(Integer, default=9)
    window_end_hour: Mapped[int] = mapped_column(Integer, default=17)
    weekdays_only: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_cap: Mapped[int] = mapped_column(Integer, default=50)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)  # first call plus two retries
    retry_gap_days: Mapped[int] = mapped_column(Integer, default=1)
    allow_voicemail: Mapped[bool] = mapped_column(Boolean, default=False)
    voicemail_text: Mapped[str] = mapped_column(Text, default="")
    ivr_policy: Mapped[str] = mapped_column(String(10), default="hangup")  # hangup or press_once
    ivr_extension: Mapped[str] = mapped_column(String(8), default="")
    require_prior_consent: Mapped[bool] = mapped_column(Boolean, default=True)  # outbound AI calls need a granted call consent on file unless the owner turns this off
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Target(Base):
    __tablename__ = "rm_target"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("rm_campaign.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(80), default="")
    last_name: Mapped[str] = mapped_column(String(80), default="")
    company: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str] = mapped_column(String(254), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    sms_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)
    demo_persona: Mapped[str] = mapped_column(String(40), default="")  # demo only: who answers in the offline run
    crm_id: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Call(Base):
    __tablename__ = "rm_call"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("rm_campaign.id"), nullable=True, index=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("rm_target.id"), nullable=True, index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("rm_agent.id"))
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("rm_prompt_version.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), default="outbound")
    peer_phone: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(12), default="placed", index=True)
    blocked_reason: Mapped[str] = mapped_column(String(60), default="")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    disposition: Mapped[str] = mapped_column(String(24), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[str] = mapped_column(String(120), default="")  # Ultravox call id
    telnyx_call_id: Mapped[str] = mapped_column(String(120), default="")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    disclosure_played: Mapped[bool] = mapped_column(Boolean, default=False)
    answered_by: Mapped[str] = mapped_column(String(12), default="")  # human, machine, ivr, none
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    taken_over: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    turns: Mapped[list[Turn]] = relationship(order_by="Turn.position", back_populates="call", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "rm_turn"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("rm_call.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(8))  # agent or caller
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    tool: Mapped[str] = mapped_column(String(40), default="")
    call: Mapped[Call] = relationship(back_populates="turns")


class Disposition(Base):
    __tablename__ = "rm_disposition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("rm_call.id"), unique=True)
    code: Mapped[str] = mapped_column(String(24), index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    set_by: Mapped[str] = mapped_column(String(12), default="agent")  # agent, rules, human
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class QAScore(Base):
    __tablename__ = "rm_qa_score"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("rm_call.id"), unique=True)
    score: Mapped[int] = mapped_column(Integer)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_note: Mapped[str] = mapped_column(String(300), default="")
    sampled: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)


class FollowUp(Base):
    __tablename__ = "rm_followup"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("rm_call.id"), index=True)
    channel: Mapped[str] = mapped_column(String(8))  # sms or email
    to: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending, sent, drafted, rejected, blocked
    blocked_reason: Mapped[str] = mapped_column(String(60), default="")
    approval_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ConsentRecord(Base):
    __tablename__ = "rm_consent"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # call, sms
    status: Mapped[str] = mapped_column(String(8))  # granted, revoked
    source: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Suppression(Base):
    __tablename__ = "rm_suppression"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True)
    reason: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
