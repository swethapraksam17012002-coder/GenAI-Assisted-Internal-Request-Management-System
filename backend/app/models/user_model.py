"""NEXUS SDLC - User SQLAlchemy Model"""

import logging
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.core.database import Base

logger = logging.getLogger("nexus.models.user")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True)
    email: Mapped[str]          = mapped_column(String(200), unique=True, nullable=False, index=True)
    full_name: Mapped[str]      = mapped_column(String(200), nullable=False)
    employee_id: Mapped[str]    = mapped_column(String(50), nullable=True)
    hashed_password: Mapped[str]= mapped_column(String(200), nullable=True)   # nullable for OAuth users
    scopes: Mapped[str]         = mapped_column(Text, default="read write")   # space-separated
    is_active: Mapped[bool]     = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool]   = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool]  = mapped_column(Boolean, default=False)
    oauth_provider: Mapped[str] = mapped_column(String(50), nullable=True)   # "google", "microsoft"
    oauth_subject: Mapped[str]  = mapped_column(String(200), nullable=True)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime]     = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]= mapped_column(DateTime(timezone=True),
                                                default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime]= mapped_column(DateTime(timezone=True),
                                                default=lambda: datetime.now(timezone.utc),
                                                onupdate=lambda: datetime.now(timezone.utc))
