"""Gmail ingestion service for importing IT mailbox messages into requests."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_model import AuditLog
from app.models.request_model import Request as RequestModel
from app.services.ai_pipeline import DEFAULT_AI_DETAILS, DEFAULT_AI_NEXT_ACTION, DEFAULT_AI_SUMMARY, run_pipeline_async
from app.services.audit_service import append_audit
from app.services.guardrails import guard_request_text

logger = logging.getLogger("nexus.email_ingestion")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
]


def gmail_ingestion_ready() -> bool:
    return bool(
        settings.GMAIL_CLIENT_SECRETS_FILE
        and settings.GMAIL_TOKEN_FILE
        and settings.GMAIL_IT_MAILBOX
        and os.path.exists(settings.GMAIL_CLIENT_SECRETS_FILE)
    )


def _req_id() -> str:
    return "REQ-" + uuid.uuid4().hex[:8].upper()


def _compute_due_date(priority: str, request_type: str, created_at: datetime) -> datetime:
    from datetime import timedelta

    hours = settings.SLA_MATRIX.get(priority, {}).get(request_type, 24)
    return created_at + timedelta(hours=hours)


def _gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token_file = settings.GMAIL_TOKEN_FILE
    client_secret_file = settings.GMAIL_CLIENT_SECRETS_FILE

    if token_file and os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode_b64(data: str | None) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_message_body(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if mime_type == "text/plain" and body_data:
        return _decode_b64(body_data)

    parts = payload.get("parts") or []
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            plain_parts.append(_decode_b64(part.get("body", {}).get("data")))
        elif part_mime == "text/html":
            html_parts.append(_decode_b64(part.get("body", {}).get("data")))
        elif part.get("parts"):
            nested = _extract_message_body(part)
            if nested:
                plain_parts.append(nested)

    if plain_parts:
        return "\n".join(filter(None, plain_parts))
    if html_parts:
        html = "\n".join(filter(None, html_parts))
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", html).strip()
    return _decode_b64(body_data)


def _headers_to_map(headers: list[dict[str, str]]) -> dict[str, str]:
    return {header.get("name", "").lower(): header.get("value", "") for header in headers}


def _build_request_payload_from_email(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload", {})
    header_map = _headers_to_map(payload.get("headers") or [])
    sender_name, sender_email = parseaddr(header_map.get("from", ""))
    subject = header_map.get("subject", "(No subject)")
    body = _extract_message_body(payload)
    combined_description = f"Email subject: {subject}\n\nEmail body:\n{body}".strip()
    requestor_name = sender_name or sender_email.split("@")[0] or "Email Requestor"
    return {
        "gmail_message_id": message.get("id"),
        "gmail_thread_id": message.get("threadId"),
        "requestor_name": requestor_name,
        "requestor_email": sender_email or settings.GMAIL_IT_MAILBOX or "unknown@example.com",
        "request_type": "Other",
        "source_channel": "Email",
        "priority": "Medium",
        "raw_description": combined_description,
    }


async def _already_ingested(db: AsyncSession, gmail_message_id: str) -> bool:
    result = await db.execute(
        select(AuditLog.id).where(
            AuditLog.event_type == "EMAIL_INGESTED",
            AuditLog.metadata_json.ilike(f'%"{gmail_message_id}"%'),
        )
    )
    return result.scalar_one_or_none() is not None


async def _create_request_from_email(db: AsyncSession, payload: dict[str, Any], created_by: str) -> RequestModel:
    guard = guard_request_text(payload["raw_description"])
    if guard.validation_errors:
        raise ValueError("; ".join(guard.validation_errors))

    now = datetime.now(timezone.utc)
    req = RequestModel(
        id=_req_id(),
        requestor_name=payload["requestor_name"],
        requestor_email=payload["requestor_email"],
        requestor_employee_id=None,
        request_type=payload["request_type"],
        source_channel="Email",
        priority=payload["priority"],
        raw_description=guard.cleaned_text,
        status="Draft",
        ai_summary=DEFAULT_AI_SUMMARY,
        ai_details=DEFAULT_AI_DETAILS,
        ai_next_action=DEFAULT_AI_NEXT_ACTION,
        ai_tags="[]",
        ai_confidence_score=0.0,
        ai_sentiment="Pending",
        ai_quality_score=0.0,
        created_at=now,
        updated_at=now,
        created_by=created_by,
        due_date=_compute_due_date(payload["priority"], payload["request_type"], now),
    )
    db.add(req)
    await db.flush()

    await append_audit(
        db,
        req.id,
        "EMAIL_INGESTED",
        None,
        json.dumps(
            {
                "gmail_message_id": payload["gmail_message_id"],
                "gmail_thread_id": payload["gmail_thread_id"],
                "source_mailbox": settings.GMAIL_IT_MAILBOX,
                "requestor_email": payload["requestor_email"],
                "subject_preview": payload["raw_description"].splitlines()[0][:200],
            }
        ),
        created_by,
        None,
        metadata_json=json.dumps(
            {
                "message_id": payload["gmail_message_id"],
                "thread_id": payload["gmail_thread_id"],
                "mailbox": settings.GMAIL_IT_MAILBOX,
            },
            separators=(",", ":"),
        ),
    )
    return req


async def _persist_ai_result(db: AsyncSession, request_id: str, result: dict[str, Any], performed_by: str):
    req_result = await db.execute(select(RequestModel).where(RequestModel.id == request_id))
    req = req_result.scalar_one_or_none()
    if not req:
        return

    req.ai_summary = result.get("ai_summary") or req.ai_summary
    req.ai_details = result.get("ai_details") or req.ai_details
    req.ai_next_action = result.get("ai_next_action") or req.ai_next_action
    req.ai_tags = json.dumps(result.get("ai_tags", []))
    req.ai_confidence_score = result.get("confidence_score", 0.0)
    req.ai_sentiment = result.get("sentiment", "Neutral")
    req.ai_quality_score = result.get("quality_score", 0.0)
    req.agent_processing_ms = result.get("processing_ms", 0)
    req.agent_pipeline_run = result.get("pipeline_run_id")
    req.updated_at = datetime.now(timezone.utc)
    await append_audit(
        db,
        req.id,
        "AI_GENERATED",
        None,
        json.dumps(
            {
                "ai_summary": req.ai_summary,
                "ai_details": req.ai_details,
                "ai_next_action": req.ai_next_action,
                "ai_tags": result.get("ai_tags", []),
                "ai_confidence_score": req.ai_confidence_score,
                "ai_sentiment": req.ai_sentiment,
                "ai_quality_score": req.ai_quality_score,
                "frameworks_used": result.get("frameworks_used", {}),
                "source_channel": "Email",
            }
        ),
        performed_by,
    )


async def sync_gmail_to_requests(db: AsyncSession, performed_by: str, *, max_messages: int | None = None) -> dict[str, Any]:
    if not gmail_ingestion_ready():
        raise RuntimeError("Gmail ingestion is not configured")

    service = _gmail_service()
    max_results = max_messages or settings.GMAIL_SYNC_MAX_MESSAGES
    mailbox = settings.GMAIL_IT_MAILBOX
    logger.info("Starting Gmail sync mailbox=%s max_messages=%s", mailbox, max_results)

    response = (
        service.users()
        .messages()
        .list(userId=mailbox, q=settings.GMAIL_QUERY, maxResults=max_results)
        .execute()
    )
    message_refs = response.get("messages", [])
    imported: list[dict[str, Any]] = []
    skipped: list[str] = []

    for message_ref in message_refs:
        message_id = message_ref.get("id")
        if not message_id:
            continue
        if await _already_ingested(db, message_id):
            skipped.append(message_id)
            continue

        message = (
            service.users()
            .messages()
            .get(userId=mailbox, id=message_id, format="full")
            .execute()
        )
        payload = _build_request_payload_from_email(message)
        req = await _create_request_from_email(db, payload, performed_by)
        result = await run_pipeline_async(
            req.id,
            {
                "raw_description": req.raw_description,
                "request_type": req.request_type,
                "priority": req.priority,
                "source_channel": req.source_channel,
                "requestor_email": req.requestor_email,
            },
            None,
        )
        await _persist_ai_result(db, req.id, result, performed_by)
        imported.append(
            {
                "request_id": req.id,
                "gmail_message_id": message_id,
                "requestor_email": req.requestor_email,
                "frameworks_used": result.get("frameworks_used", {}),
            }
        )
        (
            service.users()
            .messages()
            .modify(userId=mailbox, id=message_id, body={"removeLabelIds": ["UNREAD"]})
            .execute()
        )

    logger.info("Completed Gmail sync mailbox=%s imported=%s skipped=%s", mailbox, len(imported), len(skipped))
    return {
        "mailbox": mailbox,
        "queried": len(message_refs),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "imported": imported,
        "skipped_message_ids": skipped,
    }
