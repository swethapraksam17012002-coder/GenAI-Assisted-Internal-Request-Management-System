"""NEXUS SDLC - Audit Log + Agent Execution Models"""

import logging
from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.core.database import Base

logger = logging.getLogger("nexus.models.audit")


class AuditLog(Base):
    """Immutable event log — no UPDATE or DELETE ever performed."""
    __tablename__ = "audit_logs"

    id: Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str]    = mapped_column(String(36), ForeignKey("requests.id"), nullable=True, index=True)
    event_type: Mapped[str]    = mapped_column(String(100), nullable=False, index=True)
    old_value: Mapped[str]     = mapped_column(Text, nullable=True)
    new_value: Mapped[str]     = mapped_column(Text, nullable=True)
    performed_by: Mapped[str]  = mapped_column(String(200), nullable=True)
    ip_address: Mapped[str]    = mapped_column(String(45), nullable=True)   # IPv6 max 45 chars
    user_agent: Mapped[str]    = mapped_column(String(500), nullable=True)
    langsmith_trace_id: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)         # extra JSON context
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  default=lambda: datetime.now(timezone.utc), index=True)

    request: Mapped["Request"] = relationship("Request", back_populates="audit_logs")  # type: ignore


class AgentExecution(Base):
    """Record of every AI pipeline run."""
    __tablename__ = "agent_executions"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str]    = mapped_column(String(36), nullable=True, index=True)
    agent_name: Mapped[str]    = mapped_column(String(100), nullable=False, index=True)
    framework: Mapped[str]     = mapped_column(String(50), nullable=True)   # CrewAI | AutoGen | LangGraph
    status: Mapped[str]        = mapped_column(String(50), nullable=False)  # running|success|failed|fallback
    input_data: Mapped[str]    = mapped_column(Text, nullable=True)         # JSON
    output_data: Mapped[str]   = mapped_column(Text, nullable=True)         # JSON
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int]    = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=True)
    est_cost_usd: Mapped[float]    = mapped_column(Float, nullable=True)
    langsmith_trace_id: Mapped[str]= mapped_column(String(100), nullable=True)
    is_fallback: Mapped[bool]  = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True),
                                                    default=lambda: datetime.now(timezone.utc))


class KnowledgeChunk(Base):
    """Metadata for ChromaDB RAG index (vectors live in ChromaDB)."""
    __tablename__ = "knowledge_chunks"

    id: Mapped[str]            = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str]    = mapped_column(String(36), nullable=False, index=True)
    chunk_text: Mapped[str]    = mapped_column(Text, nullable=False)
    weight: Mapped[float]      = mapped_column(Float, default=1.0)          # 1.5 for human-corrected
    is_human_corrected: Mapped[bool] = mapped_column(Boolean, default=False)
    request_type: Mapped[str]  = mapped_column(String(50), nullable=True)
    priority: Mapped[str]      = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True),
                                                    default=lambda: datetime.now(timezone.utc))
