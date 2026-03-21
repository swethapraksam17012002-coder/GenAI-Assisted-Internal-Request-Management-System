"""NEXUS SDLC - Audit Service: append immutable audit log entries."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_model import AuditLog
from typing import Optional

logger = logging.getLogger("nexus.audit")

async def append_audit(
    db: AsyncSession,
    request_id: Optional[str],
    event_type: str,
    old_value: Optional[str],
    new_value: Optional[str],
    performed_by: Optional[str],
    ip_address: Optional[str] = None,
    langsmith_trace_id: Optional[str] = None,
    metadata_json: Optional[str] = None,
):
    log = AuditLog(
        request_id=request_id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
        performed_by=performed_by,
        ip_address=ip_address,
        langsmith_trace_id=langsmith_trace_id,
        metadata_json=metadata_json,
    )
    db.add(log)
    await db.flush()
    logger.debug("Audit appended event_type=%s request_id=%s performed_by=%s", event_type, request_id, performed_by)
    return log
