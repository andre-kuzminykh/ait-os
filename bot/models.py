"""SQLAlchemy models for the AS-IS Process Analysis bot."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from bot.states import (
    GapFieldType,
    GapStatus,
    OpportunityStatus,
    OpportunityType,
    ProcessStatus,
    SessionStatus,
)


def _utcnow():
    return datetime.now(timezone.utc)


def _gen_token():
    return uuid.uuid4().hex[:16]


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    processes = relationship("Process", back_populates="company")


class Process(Base):
    __tablename__ = "processes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(500), nullable=False)
    status = Column(
        Enum(ProcessStatus), default=ProcessStatus.CREATED, nullable=False
    )
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    company = relationship("Company", back_populates="processes")
    sessions = relationship("InterviewSession", back_populates="process")
    asis_model = relationship("AsIsModel", back_populates="process", uselist=False)
    gaps = relationship("Gap", back_populates="process")
    opportunities = relationship("AutomationOpportunity", back_populates="process")
    published_pages = relationship("PublishedPage", back_populates="process")


class Respondent(Base):
    __tablename__ = "respondents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(Integer, unique=True, nullable=False)
    display_name = Column(String(255))
    role_label = Column(String(255))
    invited_by = Column(Integer, ForeignKey("respondents.id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    sessions = relationship("InterviewSession", back_populates="respondent")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, ForeignKey("processes.id"), nullable=False)
    respondent_id = Column(Integer, ForeignKey("respondents.id"), nullable=False)
    token = Column(String(32), default=_gen_token, unique=True, nullable=False)
    state = Column(
        Enum(SessionStatus),
        default=SessionStatus.STARTED,
        nullable=False,
    )
    started_at = Column(DateTime, default=_utcnow)
    last_activity_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    process = relationship("Process", back_populates="sessions")
    respondent = relationship("Respondent", back_populates="sessions")
    raw_inputs = relationship("RawInput", back_populates="session")


class RawInput(Base):
    __tablename__ = "raw_inputs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    message_type = Column(String(20), nullable=False)  # text | voice | audio
    telegram_message_id = Column(Integer, nullable=True)
    raw_text = Column(Text, nullable=True)
    file_ref = Column(String(500), nullable=True)
    transcript_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("InterviewSession", back_populates="raw_inputs")


class AsIsModel(Base):
    __tablename__ = "asis_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, ForeignKey("processes.id"), unique=True, nullable=False)
    version = Column(Integer, default=1)
    goal = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    triggers = Column(Text, nullable=True)  # JSON list
    inputs = Column(Text, nullable=True)  # JSON list
    outputs = Column(Text, nullable=True)  # JSON list
    stages = Column(Text, nullable=True)  # JSON list of stage objects
    roles = Column(Text, nullable=True)  # JSON list
    systems = Column(Text, nullable=True)  # JSON list
    artifacts = Column(Text, nullable=True)  # JSON list
    metrics = Column(Text, nullable=True)  # JSON list
    pain_points = Column(Text, nullable=True)  # JSON list
    handoffs = Column(Text, nullable=True)  # JSON list
    completeness_score = Column(Float, default=0.0)
    generated_at = Column(DateTime, default=_utcnow)

    process = relationship("Process", back_populates="asis_model")


class Gap(Base):
    __tablename__ = "gaps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, ForeignKey("processes.id"), nullable=False)
    stage_id = Column(String(100), nullable=True)
    field_type = Column(Enum(GapFieldType), nullable=False)
    question_text = Column(Text, nullable=False)
    confidence_score = Column(Float, default=0.0)
    status = Column(Enum(GapStatus), default=GapStatus.PENDING, nullable=False)
    answer_ref = Column(Integer, ForeignKey("raw_inputs.id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    process = relationship("Process", back_populates="gaps")


class AutomationOpportunity(Base):
    __tablename__ = "automation_opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, ForeignKey("processes.id"), nullable=False)
    stage_id = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    opp_type = Column(Enum(OpportunityType), nullable=True)
    problem = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    expected_benefit = Column(Text, nullable=True)
    status = Column(
        Enum(OpportunityStatus),
        default=OpportunityStatus.PROPOSED,
        nullable=False,
    )
    created_at = Column(DateTime, default=_utcnow)

    process = relationship("Process", back_populates="opportunities")


class PublishedPage(Base):
    __tablename__ = "published_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    process_id = Column(Integer, ForeignKey("processes.id"), nullable=False)
    token = Column(String(32), default=_gen_token, unique=True, nullable=False)
    asis_version = Column(Integer, default=1)
    mermaid_code = Column(Text, nullable=True)
    narrative_html = Column(Text, nullable=True)
    html_url = Column(String(500), nullable=True)
    pdf_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    process = relationship("Process", back_populates="published_pages")
