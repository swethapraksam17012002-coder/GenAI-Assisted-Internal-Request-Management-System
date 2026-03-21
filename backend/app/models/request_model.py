"""NEXUS SDLC - Request SQLAlchemy Models"""

import logging
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import enum
from app.core.database import Base

logger = logging.getLogger("nexus.models.request")


class RequestTypeEnum(str, enum.Enum):
    Access = "Access"
    Issue = "Issue"
    Information = "Information"
    Change = "Change"
    Other = "Other"


class SourceChannelEnum(str, enum.Enum):
    Email = "Email"
    Portal = "Portal"
    Chat = "Chat"
    Form = "Form"
    Ticketing = "Ticketing"


class PriorityEnum(str, enum.Enum):
    Low = "Low"
    Medium = "Medium"
    High = "High"
    Critical = "Critical"


class StatusEnum(str, enum.Enum):
    Draft = "Draft"
    Reviewed = "Reviewed"
    Approved = "Approved"
    InProgress = "In Progress"
    Completed = "Completed"
    Overdue = "Overdue"
    Cancelled = "Cancelled"


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str]                = mapped_column(String(36), primary_key=True)
    requestor_name: Mapped[str]    = mapped_column(String(200), nullable=False)
    requestor_email: Mapped[str]   = mapped_column(String(200), nullable=False, index=True)
    requestor_employee_id: Mapped[str] = mapped_column(String(50), nullable=True)
    request_type: Mapped[str]      = mapped_column(String(50), nullable=False, index=True)
    source_channel: Mapped[str]    = mapped_column(String(50), nullable=False)
    priority: Mapped[str]          = mapped_column(String(50), nullable=False, index=True)
    raw_description: Mapped[str]   = mapped_column(Text, nullable=False)     # IMMUTABLE
    status: Mapped[str]            = mapped_column(String(50), nullable=False, default="Draft", index=True)

    # AI-generated fields
    ai_summary: Mapped[str]        = mapped_column(Text, nullable=True)
    ai_details: Mapped[str]        = mapped_column(Text, nullable=True)
    ai_next_action: Mapped[str]    = mapped_column(Text, nullable=True)
    ai_tags: Mapped[str]           = mapped_column(Text, nullable=True)        # JSON array string
    ai_confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_sentiment: Mapped[str]      = mapped_column(String(50), nullable=True)
    ai_rag_context: Mapped[str]    = mapped_column(Text, nullable=True)        # JSON
    ai_quality_score: Mapped[float]= mapped_column(Float, nullable=True)
    agent_pipeline_run: Mapped[str]= mapped_column(String(100), nullable=True)
    agent_processing_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    langsmith_trace_id: Mapped[str]= mapped_column(String(100), nullable=True)

    # Workflow fields
    reviewed_by: Mapped[str]       = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str]       = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str]       = mapped_column(String(200), nullable=True)
    cancelled_by: Mapped[str]      = mapped_column(String(200), nullable=True)
    cancelled_reason: Mapped[str]  = mapped_column(Text, nullable=True)
    due_date: Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=True)
    is_overdue: Mapped[bool]       = mapped_column(Boolean, default=False)

    # Metadata
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True),
                                                   default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True),
                                                   default=lambda: datetime.now(timezone.utc),
                                                   onupdate=lambda: datetime.now(timezone.utc))
    created_by: Mapped[str]        = mapped_column(String(200), nullable=True)  # user ID from JWT

    # Relationships
    follow_ups: Mapped[list] = relationship("FollowUp", back_populates="request", cascade="all, delete-orphan")
    audit_logs: Mapped[list] = relationship("AuditLog", back_populates="request")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str]    = mapped_column(String(36), ForeignKey("requests.id"), nullable=False, index=True)
    comment: Mapped[str]       = mapped_column(Text, nullable=False)
    created_by: Mapped[str]    = mapped_column(String(200), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True),
                                                    default=lambda: datetime.now(timezone.utc))

    request: Mapped["Request"] = relationship("Request", back_populates="follow_ups")
