"""
NEXUS SDLC - Requests Router
Full request lifecycle: create, read, update, workflow transitions,
follow-ups, audit trail, SSE streaming, AI pipeline trigger.
All endpoints protected by JWT scopes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Security, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, EmailStr, field_validator
from typing import Any, Optional
from datetime import datetime, timezone
import uuid
import json
import asyncio
import logging
import re

from app.core.database import get_db
from app.core.security import get_current_user, TokenData, decode_token
from app.models.request_model import Request as RequestModel, FollowUp
from app.models.audit_model import AuditLog
from app.services.audit_service import append_audit
from app.services.ai_pipeline import run_pipeline_async, run_pipeline_fallback
from app.services.guardrails import guard_request_text, sanitize_free_text_output, sanitize_user_text
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger("nexus.requests")

DEFAULT_AI_SUMMARY = "AI analysis in progress."
DEFAULT_AI_DETAILS = "AI analysis is queued or running for this request."
DEFAULT_AI_NEXT_ACTION = "Await AI analysis completion and review the generated notes."

# SSE queues: request_id → asyncio.Queue
_sse_queues: dict[str, asyncio.Queue] = {}


# ── Schemas ───────────────────────────────────────────────────────────────────
class RequestCreate(BaseModel):
    requestor_name: str
    requestor_email: EmailStr
    requestor_employee_id: Optional[str] = None
    request_type: str
    source_channel: str
    priority: str
    raw_description: str

    @field_validator("requestor_name")
    @classmethod
    def name_not_empty(cls, v):
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("Name must be 1-200 characters")
        return v

    @field_validator("raw_description")
    @classmethod
    def desc_length(cls, v):
        cleaned = sanitize_user_text(v, max_length=10_000)
        if len(cleaned) < 10 or len(cleaned) > 10_000:
            raise ValueError("Description must be 10-10,000 characters")
        guard = guard_request_text(cleaned)
        if guard.validation_errors:
            raise ValueError("; ".join(guard.validation_errors))
        return cleaned

    @field_validator("request_type")
    @classmethod
    def valid_type(cls, v):
        valid = {"Access","Issue","Information","Change","Other"}
        if v not in valid:
            raise ValueError(f"request_type must be one of {valid}")
        return v

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, v):
        valid = {"Low","Medium","High","Critical"}
        if v not in valid:
            raise ValueError(f"priority must be one of {valid}")
        return v

    @field_validator("source_channel")
    @classmethod
    def valid_channel(cls, v):
        valid = {"Email","Portal","Chat","Form","Ticketing"}
        if v not in valid:
            raise ValueError(f"source_channel must be one of {valid}")
        return v


class RequestUpdate(BaseModel):
    status: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_details: Optional[str] = None
    ai_next_action: Optional[str] = None
    reviewed_by: Optional[str] = None
    approved_by: Optional[str] = None


class RequestDraftFromText(BaseModel):
    raw_text: str
    source_channel: str = "Chat"

    @field_validator("raw_text")
    @classmethod
    def validate_raw_text(cls, v):
        cleaned = sanitize_user_text(v, max_length=10_000)
        if len(cleaned) < 10:
            raise ValueError("Text content must be at least 10 characters")
        return cleaned

    @field_validator("source_channel")
    @classmethod
    def validate_draft_channel(cls, v):
        valid = {"Chat", "Ticketing"}
        if v not in valid:
            raise ValueError(f"source_channel must be one of {valid}")
        return v


class RequestDraftFromFormJson(BaseModel):
    json_payload: dict[str, Any]


class FollowUpCreate(BaseModel):
    comment: str
    created_by: str

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v):
        cleaned = sanitize_free_text_output(v, max_length=1500)
        if len(cleaned) < 3:
            raise ValueError("Comment must be at least 3 characters")
        return cleaned

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v):
        cleaned = sanitize_user_text(v, max_length=200)
        if len(cleaned) < 1:
            raise ValueError("created_by is required")
        return cleaned


class WorkflowAction(BaseModel):
    performed_by: str
    notes: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("performed_by")
    @classmethod
    def validate_performed_by(cls, v):
        cleaned = sanitize_user_text(v, max_length=200)
        if len(cleaned) < 1:
            raise ValueError("performed_by is required")
        return cleaned

    @field_validator("notes", "reason")
    @classmethod
    def validate_optional_text(cls, v):
        if v is None:
            return v
        cleaned = sanitize_free_text_output(v, max_length=1000)
        return cleaned or None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _req_id() -> str:
    return "REQ-" + uuid.uuid4().hex[:8].upper()


def _compute_due_date(priority: str, request_type: str, created_at: datetime) -> datetime:
    from datetime import timedelta
    hours = settings.SLA_MATRIX.get(priority, {}).get(request_type, 24)
    return created_at + timedelta(hours=hours)


async def _get_request_or_404(db: AsyncSession, request_id: str) -> RequestModel:
    result = await db.execute(
        select(RequestModel)
        .options(
            selectinload(RequestModel.follow_ups),
            selectinload(RequestModel.audit_logs),
        )
        .where(RequestModel.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
    return req


def _is_immutable(req: RequestModel) -> bool:
    return req.status in ("Approved", "Completed")


def _non_empty_ai_text(value: Optional[str], fallback: str) -> str:
    text = (value or "").strip()
    return text or fallback


def _guess_request_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("access", "vpn", "permission", "grant", "login", "account")):
        return "Access"
    if any(word in lowered for word in ("error", "issue", "problem", "unable", "failed", "not working", "down")):
        return "Issue"
    if any(word in lowered for word in ("change", "update", "modify", "migrate", "deploy")):
        return "Change"
    if any(word in lowered for word in ("policy", "information", "how many", "what is", "details", "leave")):
        return "Information"
    return "Other"


def _guess_priority(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("critical", "sev1", "production down", "outage", "p1")):
        return "Critical"
    if any(word in lowered for word in ("urgent", "asap", "production", "hotfix", "high priority", "immediately")):
        return "High"
    if any(word in lowered for word in ("whenever", "low priority", "minor")):
        return "Low"
    return "Medium"


def _extract_requestor_details_from_text(text: str) -> tuple[str, str]:
    labeled_match = re.search(
        r"(?im)^(?:requested by|opened by|raised by|submitted by)\s*:\s*([^<\n]+?)(?:\s*<\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\s*>)?\s*$",
        text,
    )
    if labeled_match:
        labeled_name = labeled_match.group(1).strip(" -:\t")
        labeled_email = (labeled_match.group(2) or "").strip()
        if labeled_name:
            return labeled_name, labeled_email

    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, flags=re.IGNORECASE)
    email = email_match.group(0) if email_match else ""

    name = ""
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        if line.endswith(":"):
            continue
        if line.lower().startswith(("regards", "thanks", "thank you", "best")):
            continue
        if 1 <= len(line.split()) <= 4 and "@" not in line and len(line) <= 60:
            name = line
            break

    if not name and email:
        name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
    return name, email


async def _build_request_draft_response(
    payload: dict,
    fallback_name: str = "",
    fallback_email: str = "",
) -> dict:
    if settings.OLLAMA_MODEL:
        draft_result = await run_pipeline_async("DRAFT", payload, None)
    else:
        draft_result = await run_pipeline_fallback("DRAFT", payload, None)

    return {
        "requestor_name": payload.get("requestor_name") or fallback_name,
        "requestor_email": payload.get("requestor_email") or fallback_email,
        "request_type": payload.get("request_type"),
        "priority": payload.get("priority"),
        "source_channel": payload.get("source_channel"),
        "raw_description": draft_result.get("ai_details") or payload.get("raw_description"),
        "ai_summary_preview": draft_result.get("ai_summary", ""),
        "ai_next_action_preview": draft_result.get("ai_next_action", ""),
        "ai_tags_preview": draft_result.get("ai_tags", []),
        "frameworks_used": draft_result.get("frameworks_used", {}),
    }


async def _index_request_for_rag(req: RequestModel):
    try:
        from app.services.rag_service import index_request

        index_text = "\n".join(
            part for part in [
                req.raw_description or "",
                req.ai_summary or "",
                req.ai_details or "",
                req.ai_next_action or "",
            ]
            if part
        )
        await index_request(
            req.id,
            index_text,
            {
                "request_type": req.request_type,
                "source_channel": req.source_channel,
                "priority": req.priority,
                "status": req.status,
                "created_by": req.created_by,
            },
        )
    except Exception as exc:
        logger.warning("RAG indexing failed for %s: %s", req.id, exc)


# ── POST /api/requests/ ──────────────────────────────────────────────────────
@router.post("/", status_code=201)
async def create_request(
    body: RequestCreate,
    background_tasks: BackgroundTasks,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    guard = guard_request_text(body.raw_description)
    if guard.validation_errors:
        raise HTTPException(status_code=422, detail="; ".join(guard.validation_errors))
    logger.info("Request creation started requester=%s type=%s priority=%s", token.sub, body.request_type, body.priority)

    now = datetime.now(timezone.utc)
    req = RequestModel(
        id=_req_id(),
        requestor_name=body.requestor_name,
        requestor_email=body.requestor_email,
        requestor_employee_id=body.requestor_employee_id,
        request_type=body.request_type,
        source_channel=body.source_channel,
        priority=body.priority,
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
        created_by=token.sub,
        due_date=_compute_due_date(body.priority, body.request_type, now),
    )
    db.add(req)
    await db.flush()

    await append_audit(db, req.id, "REQUEST_CREATED", None,
                       body.model_dump_json(), token.sub,
                       http_request.client.host if http_request.client else None)

    # Queue SSE channel + background AI pipeline
    _sse_queues[req.id] = asyncio.Queue()
    pipeline_payload = body.model_dump()
    pipeline_payload["raw_description"] = guard.cleaned_text
    background_tasks.add_task(_run_ai_pipeline, req.id, pipeline_payload, token.sub)
    logger.info("Request created id=%s requester=%s", req.id, token.sub)

    return {
        "success": True,
        "data": {
            "request": {"id": req.id, "status": req.status, "due_date": req.due_date.isoformat()},
            "ai_metadata": {"status": "pipeline_queued", "framework": "LangGraph+CrewAI"},
        },
        "error": None,
    }


@router.post("/draft-from-text")
async def create_request_draft_from_text(
    body: RequestDraftFromText,
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    guard = guard_request_text(body.raw_text)
    if guard.validation_errors:
        raise HTTPException(status_code=422, detail="; ".join(guard.validation_errors))

    guessed_name, guessed_email = _extract_requestor_details_from_text(guard.cleaned_text)
    guessed_type = _guess_request_type(guard.cleaned_text)
    guessed_priority = _guess_priority(guard.cleaned_text)
    payload = {
        "raw_description": guard.cleaned_text,
        "request_type": guessed_type,
        "priority": guessed_priority,
        "source_channel": body.source_channel,
        "requestor_email": guessed_email,
        "requestor_name": guessed_name,
    }

    logger.info("Draft prefill requested requester=%s source_channel=%s", token.sub, body.source_channel)
    return {
        "success": True,
        "data": await _build_request_draft_response(payload, guessed_name, guessed_email),
        "error": None,
    }


@router.post("/draft-from-form-json")
async def create_request_draft_from_form_json(
    body: RequestDraftFromFormJson,
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    payload = dict(body.json_payload or {})
    payload["source_channel"] = "Form"

    try:
        normalized = RequestCreate.model_validate(payload).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("Form draft prefill requested requester=%s source_channel=Form", token.sub)
    return {
        "success": True,
        "data": await _build_request_draft_response(
            normalized,
            normalized.get("requestor_name", ""),
            normalized.get("requestor_email", ""),
        ),
        "error": None,
    }


async def _run_ai_pipeline(request_id: str, payload: dict, user_id: str):
    """Background task: run AI pipeline and push SSE events."""
    queue = _sse_queues.get(request_id)
    try:
        if settings.OLLAMA_MODEL:
            result = await run_pipeline_async(request_id, payload, queue)
        else:
            result = await run_pipeline_fallback(request_id, payload, queue)

        # Persist AI results
        async with __import__("app.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as db:
            req_result = await db.execute(select(RequestModel).where(RequestModel.id == request_id))
            req = req_result.scalar_one_or_none()
            if req:
                req.ai_summary = _non_empty_ai_text(result.get("ai_summary"), req.ai_summary or DEFAULT_AI_SUMMARY)
                req.ai_details = _non_empty_ai_text(result.get("ai_details"), req.ai_details or DEFAULT_AI_DETAILS)
                req.ai_next_action = _non_empty_ai_text(result.get("ai_next_action"), req.ai_next_action or DEFAULT_AI_NEXT_ACTION)
                req.ai_tags = json.dumps(result.get("ai_tags", []))
                req.ai_confidence_score = result.get("confidence_score", 0.0)
                req.ai_sentiment = result.get("sentiment", "Neutral")
                req.ai_rag_context = result.get("rag_context", "[]")
                req.ai_quality_score = result.get("quality_score", 0.0)
                req.agent_processing_ms = result.get("processing_ms", 0)
                req.agent_pipeline_run = result.get("pipeline_run_id")
                req.langsmith_trace_id = result.get("langsmith_trace_id")
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
                            "ai_rag_context": req.ai_rag_context,
                            "ai_quality_score": req.ai_quality_score,
                            "frameworks_used": result.get("frameworks_used", {}),
                        }
                    ),
                    user_id,
                    None,
                    result.get("langsmith_trace_id"),
                )
                await _index_request_for_rag(req)
                await db.commit()
    except Exception as e:
        logger.error(f"AI pipeline error for {request_id}: {e}", exc_info=True)
    finally:
        if queue:
            await queue.put({"event": "pipeline_done", "data": {"request_id": request_id}})


# ── GET /api/requests/ ───────────────────────────────────────────────────────
@router.get("/")
async def list_requests(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    request_type: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    filters = []
    if status:
        filters.append(RequestModel.status == status)
    if priority:
        filters.append(RequestModel.priority == priority)
    if request_type:
        filters.append(RequestModel.request_type == request_type)
    if channel:
        filters.append(RequestModel.source_channel == channel)
    if overdue_only:
        filters.append(RequestModel.is_overdue == True)
    if search:
        term = f"%{search}%"
        filters.append(or_(
            RequestModel.id.ilike(term),
            RequestModel.requestor_name.ilike(term),
            RequestModel.requestor_email.ilike(term),
            RequestModel.ai_summary.ilike(term),
        ))

    count_q = select(func.count()).select_from(RequestModel)
    if filters:
        count_q = count_q.where(and_(*filters))
    total = (await db.execute(count_q)).scalar_one()

    q = select(RequestModel).order_by(RequestModel.created_at.desc()).offset(skip).limit(limit)
    if filters:
        q = q.where(and_(*filters))
    rows = (await db.execute(q)).scalars().all()

    return {"success": True, "data": {
        "total": total, "skip": skip, "limit": limit,
        "requests": [_req_to_dict(r) for r in rows],
    }, "error": None}


# ── GET /api/requests/{id} ───────────────────────────────────────────────────
@router.get("/{request_id}")
async def get_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    req = await _get_request_or_404(db, request_id)
    d = _req_to_dict(req)
    follow_ups = req.follow_ups if isinstance(req.follow_ups, list) else ([req.follow_ups] if req.follow_ups else [])
    audit_logs = req.audit_logs if isinstance(req.audit_logs, list) else ([req.audit_logs] if req.audit_logs else [])
    d["follow_ups"] = [_fu_to_dict(f) for f in follow_ups]
    d["audit_logs"] = [_audit_to_dict(a) for a in audit_logs[-50:]]
    d["frameworks_used"] = _extract_frameworks_used(audit_logs)
    d["pipeline_status"] = "running" if request_id in _sse_queues else "idle"
    return {"success": True, "data": d, "error": None}


# ── PATCH /api/requests/{id} ─────────────────────────────────────────────────
@router.patch("/{request_id}")
async def update_request(
    request_id: str,
    body: RequestUpdate,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    if _is_immutable(req):
        raise HTTPException(403, "Approved/Completed requests are read-only")

    changes = {}
    for field, val in body.model_dump(exclude_none=True).items():
        if isinstance(val, str):
            max_length = 2500 if field in {"ai_summary", "ai_details", "ai_next_action"} else 200
            val = sanitize_free_text_output(val, max_length=max_length)
        old = getattr(req, field, None)
        setattr(req, field, val)
        changes[field] = {"old": old, "new": val}

    req.updated_at = datetime.now(timezone.utc)
    await append_audit(db, req.id, "REQUEST_UPDATED", json.dumps({k: v["old"] for k,v in changes.items()}),
                       json.dumps({k: v["new"] for k,v in changes.items()}), token.sub,
                       http_request.client.host if http_request.client else None)
    return {"success": True, "data": _req_to_dict(req), "error": None}


@router.post("/{request_id}/regenerate-ai")
async def regenerate_ai(
    request_id: str,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    logger.info("AI regenerate requested request_id=%s requester=%s", request_id, token.sub)
    payload = {
        "raw_description": req.raw_description,
        "request_type": req.request_type,
        "priority": req.priority,
        "source_channel": req.source_channel,
        "requestor_email": req.requestor_email,
    }

    if settings.OLLAMA_MODEL:
        result = await run_pipeline_async(request_id, payload, None)
    else:
        result = await run_pipeline_fallback(request_id, payload, None)

    previous_ai = {
        "ai_summary": req.ai_summary,
        "ai_details": req.ai_details,
        "ai_next_action": req.ai_next_action,
        "ai_tags": req.ai_tags,
        "ai_confidence_score": req.ai_confidence_score,
        "ai_sentiment": req.ai_sentiment,
        "ai_rag_context": req.ai_rag_context,
        "ai_quality_score": req.ai_quality_score,
    }

    req.ai_summary = _non_empty_ai_text(result.get("ai_summary"), req.ai_summary or DEFAULT_AI_SUMMARY)
    req.ai_details = _non_empty_ai_text(result.get("ai_details"), req.ai_details or DEFAULT_AI_DETAILS)
    req.ai_next_action = _non_empty_ai_text(result.get("ai_next_action"), req.ai_next_action or DEFAULT_AI_NEXT_ACTION)
    req.ai_tags = json.dumps(result.get("ai_tags", []))
    req.ai_confidence_score = result.get("confidence_score", 0.0)
    req.ai_sentiment = result.get("sentiment", "Neutral")
    req.ai_rag_context = result.get("rag_context", "[]")
    req.ai_quality_score = result.get("quality_score", 0.0)
    req.agent_processing_ms = result.get("processing_ms", 0)
    req.agent_pipeline_run = result.get("pipeline_run_id")
    req.langsmith_trace_id = result.get("langsmith_trace_id")
    req.updated_at = datetime.now(timezone.utc)

    await append_audit(
        db,
        req.id,
        "AI_REGENERATED",
        json.dumps(previous_ai),
        json.dumps(
            {
                "ai_summary": req.ai_summary,
                "ai_details": req.ai_details,
                "ai_next_action": req.ai_next_action,
                "ai_tags": result.get("ai_tags", []),
                "ai_confidence_score": req.ai_confidence_score,
                "ai_sentiment": req.ai_sentiment,
                "ai_rag_context": req.ai_rag_context,
                "ai_quality_score": req.ai_quality_score,
                "frameworks_used": result.get("frameworks_used", {}),
            }
        ),
        token.sub,
        http_request.client.host if http_request.client else None,
        result.get("langsmith_trace_id"),
    )
    await _index_request_for_rag(req)
    response_data = _req_to_dict(req)
    response_data["frameworks_used"] = result.get("frameworks_used", {})
    logger.info(
        "AI regenerate completed request_id=%s requester=%s generation=%s",
        request_id,
        token.sub,
        result.get("frameworks_used", {}).get("generation"),
    )
    return {"success": True, "data": response_data, "error": None}


# ── POST /api/requests/{id}/review ───────────────────────────────────────────
@router.post("/{request_id}/review")
async def review_request(
    request_id: str,
    body: WorkflowAction,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    if req.status not in ("Draft",):
        raise HTTPException(400, f"Cannot review a request in '{req.status}' status")
    req.status = "Reviewed"
    req.reviewed_by = body.performed_by
    req.reviewed_at = datetime.now(timezone.utc)
    req.updated_at = datetime.now(timezone.utc)
    await append_audit(db, req.id, "STATUS_CHANGED", "Draft", "Reviewed", token.sub,
                       http_request.client.host if http_request.client else None)
    return {"success": True, "data": _req_to_dict(req), "error": None}


# ── POST /api/requests/{id}/approve ─────────────────────────────────────────
@router.post("/{request_id}/approve")
async def approve_request(
    request_id: str,
    body: WorkflowAction,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    if req.status != "Reviewed":
        raise HTTPException(400, f"Request must be in 'Reviewed' state before approval")
    req.status = "Approved"
    req.approved_by = body.performed_by
    req.approved_at = datetime.now(timezone.utc)
    req.updated_at = datetime.now(timezone.utc)
    await append_audit(db, req.id, "STATUS_CHANGED", "Reviewed", "Approved", token.sub,
                       http_request.client.host if http_request.client else None)
    return {"success": True, "data": _req_to_dict(req), "error": None}


# ── POST /api/requests/{id}/complete ─────────────────────────────────────────
@router.post("/{request_id}/complete")
async def complete_request(
    request_id: str,
    body: WorkflowAction,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    req.status = "Completed"
    req.resolved_by = body.performed_by
    req.resolved_at = datetime.now(timezone.utc)
    req.updated_at = datetime.now(timezone.utc)
    await append_audit(db, req.id, "STATUS_CHANGED", req.status, "Completed", token.sub,
                       http_request.client.host if http_request.client else None)
    return {"success": True, "data": _req_to_dict(req), "error": None}


# ── POST /api/requests/{id}/cancel ───────────────────────────────────────────
@router.post("/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    body: WorkflowAction,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    if _is_immutable(req):
        raise HTTPException(403, "Cannot cancel an Approved/Completed request")
    old_status = req.status
    req.status = "Cancelled"
    req.cancelled_by = body.performed_by
    req.cancelled_reason = body.reason
    req.updated_at = datetime.now(timezone.utc)
    await append_audit(db, req.id, "STATUS_CHANGED", old_status, "Cancelled", token.sub,
                       http_request.client.host if http_request.client else None)
    return {"success": True, "data": _req_to_dict(req), "error": None}


# ── POST /api/requests/{id}/followups ────────────────────────────────────────
@router.post("/{request_id}/followups", status_code=201)
async def add_followup(
    request_id: str,
    body: FollowUpCreate,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    req = await _get_request_or_404(db, request_id)
    if req.status == "Cancelled":
        raise HTTPException(400, "Cannot add follow-up to a cancelled request")
    fu = FollowUp(
        request_id=request_id,
        comment=body.comment,
        created_by=body.created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(fu)
    await db.flush()
    logger.info("Follow-up added request_id=%s followup_id=%s created_by=%s", request_id, fu.id, body.created_by)
    return {"success": True, "data": {"followup_id": fu.id}, "error": None}


# ── PATCH /api/requests/{id}/followups/{fid}/complete ────────────────────────
@router.patch("/{request_id}/followups/{followup_id}/complete")
async def complete_followup(
    request_id: str,
    followup_id: int,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["write"]),
):
    result = await db.execute(
        select(FollowUp).where(FollowUp.id == followup_id, FollowUp.request_id == request_id)
    )
    fu = result.scalar_one_or_none()
    if not fu:
        raise HTTPException(404, "Follow-up not found")
    fu.is_completed = True
    fu.completed_at = datetime.now(timezone.utc)
    logger.info("Follow-up completed request_id=%s followup_id=%s completed_by=%s", request_id, followup_id, token.sub)
    return {"success": True, "data": {"completed_at": fu.completed_at.isoformat()}, "error": None}


# ── GET /api/requests/{id}/stream (SSE) ──────────────────────────────────────
@router.get("/{request_id}/stream")
async def stream_request(
    request_id: str,
    token: Optional[str] = Query(None),
):
    """Server-Sent Events: streams AI pipeline progress for a request."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing stream token")

    token_data = decode_token(token)
    if token_data.token_type != "access":
        raise HTTPException(status_code=401, detail="Invalid stream token type")
    if "read" not in token_data.scopes:
        raise HTTPException(status_code=403, detail="Insufficient permissions. Required scope: 'read'")

    queue = _sse_queues.get(request_id)
    if not queue:
        # Request already processed — send immediate done
        async def _done():
            yield "event: pipeline_done\ndata: {}\n\n"
        return StreamingResponse(_done(), media_type="text/event-stream")

    async def _event_generator():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {msg.get('event','message')}\ndata: {json.dumps(msg.get('data',{}))}\n\n"
                    if msg.get("event") in ("pipeline_done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_queues.pop(request_id, None)

    return StreamingResponse(_event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── GET /api/requests/{id}/audit ─────────────────────────────────────────────
@router.get("/{request_id}/audit")
async def get_audit_trail(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    result = await db.execute(
        select(AuditLog).where(AuditLog.request_id == request_id).order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    return {"success": True, "data": [_audit_to_dict(a) for a in logs], "error": None}


# ── Serialisers ───────────────────────────────────────────────────────────────
def _req_to_dict(r: RequestModel) -> dict:
    return {
        "id": r.id, "requestor_name": r.requestor_name, "requestor_email": r.requestor_email,
        "requestor_employee_id": r.requestor_employee_id, "request_type": r.request_type,
        "source_channel": r.source_channel, "priority": r.priority, "status": r.status,
        "raw_description": r.raw_description, "ai_summary": r.ai_summary,
        "ai_details": r.ai_details, "ai_next_action": r.ai_next_action,
        "ai_tags": json.loads(r.ai_tags) if r.ai_tags else [],
        "ai_confidence_score": r.ai_confidence_score, "ai_sentiment": r.ai_sentiment,
        "ai_quality_score": r.ai_quality_score, "agent_processing_ms": r.agent_processing_ms,
        "agent_pipeline_run": r.agent_pipeline_run,
        "langsmith_trace_id": r.langsmith_trace_id,
        "reviewed_by": r.reviewed_by, "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "approved_by": r.approved_by, "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "is_overdue": r.is_overdue,
        "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat(),
    }


def _fu_to_dict(f: FollowUp) -> dict:
    return {
        "id": f.id, "comment": f.comment, "created_by": f.created_by,
        "is_completed": f.is_completed,
        "completed_at": f.completed_at.isoformat() if f.completed_at else None,
        "created_at": f.created_at.isoformat(),
    }


def _audit_to_dict(a: AuditLog) -> dict:
    return {
        "id": a.id, "event_type": a.event_type,
        "old_value": a.old_value, "new_value": a.new_value,
        "performed_by": a.performed_by,
        "langsmith_trace_id": a.langsmith_trace_id,
        "created_at": a.created_at.isoformat(),
    }


def _extract_frameworks_used(audit_logs: list[AuditLog]) -> dict:
    ai_events = {"AI_REGENERATED", "AI_GENERATED"}
    for audit in reversed(audit_logs if isinstance(audit_logs, list) else []):
        if audit.event_type not in ai_events or not audit.new_value:
            continue
        try:
            payload = json.loads(audit.new_value)
        except Exception:
            continue
        frameworks = payload.get("frameworks_used")
        if isinstance(frameworks, dict):
            return frameworks
    return {}
