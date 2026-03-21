"""NEXUS SDLC - AI Agents Router"""

from fastapi import APIRouter, Depends, HTTPException, Security, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.audit_model import AgentExecution
from app.services.code_quality import run_code_quality, DEFAULT_CHECKLIST
from app.services.rag_service import retrieve_similar, purge_collection, get_stats
from app.core.config import settings
from app.services.ai_frameworks import (
    autogen_available,
    autogen_ready,
    crewai_available,
    crewai_ready,
    litellm_available,
    ollama_available,
)

router = APIRouter()
logger = logging.getLogger("nexus.agents")


class CodeQualityRequest(BaseModel):
    code: str
    language: str = "python"
    custom_checklist: Optional[list] = None


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 3
    filter: Optional[dict] = None


@router.get("/status")
async def agent_status(token: TokenData = Security(get_current_user, scopes=["read"])):
    """Report health of all AI framework components."""
    rag_stats = await get_stats()
    if crewai_ready():
        crewai_status = "configured"
    elif not crewai_available():
        crewai_status = "package_missing"
    elif not litellm_available():
        crewai_status = "litellm_missing"
    elif not ollama_available():
        crewai_status = "llm_not_configured"
    else:
        crewai_status = "fallback_mode"
    return {
        "success": True,
        "data": {
            "crewai":    {"status": crewai_status},
            "autogen":   {"status": "configured" if autogen_ready() else ("package_missing" if not autogen_available() else "fallback_mode")},
            "langchain": {"status": "configured" if settings.OLLAMA_MODEL else "fallback_mode"},
            "langsmith": {"status": "enabled" if settings.LANGSMITH_TRACING else "disabled"},
            "chromadb":  {"status": "ready" if rag_stats.get("available") else "unavailable", **rag_stats},
            "llm_api":   {"status": "connected" if settings.OLLAMA_MODEL else "not_configured"},
        },
        "error": None,
    }


@router.post("/code-quality")
async def code_quality(
    body: CodeQualityRequest,
    token: TokenData = Security(get_current_user, scopes=["agents:exec"]),
):
    logger.info("Code quality analysis requested language=%s requester=%s", body.language, token.sub)
    result = run_code_quality(body.code, body.language, body.custom_checklist)
    logger.info(
        "Code quality analysis completed requester=%s status=%s grade=%s score=%s",
        token.sub,
        result.get("framework_runtime", {}).get("status"),
        result.get("summary", {}).get("grade"),
        result.get("summary", {}).get("score"),
    )
    return {"success": True, "data": result, "error": None}


@router.get("/checklist")
async def get_checklist(token: TokenData = Security(get_current_user, scopes=["read"])):
    return {"success": True, "data": DEFAULT_CHECKLIST, "error": None}


@router.post("/rag/search")
async def rag_search(
    body: RAGSearchRequest,
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.info("RAG search requested requester=%s top_k=%s", token.sub, body.top_k)
    results = await retrieve_similar(body.query, body.top_k, body.filter)
    logger.info("RAG search completed requester=%s result_count=%s", token.sub, len(results))
    return {"success": True, "data": {"results": results, "count": len(results)}, "error": None}


@router.get("/rag/stats")
async def rag_stats(token: TokenData = Security(get_current_user, scopes=["read"])):
    stats = await get_stats()
    return {"success": True, "data": stats, "error": None}


@router.delete("/rag/purge")
async def rag_purge(
    confirm: bool = Query(False),
    token: TokenData = Security(get_current_user, scopes=["rag:admin"]),
):
    if not confirm:
        raise HTTPException(400, "Must pass ?confirm=true to purge the knowledge base")
    logger.warning("RAG purge requested by %s", token.sub)
    await purge_collection()
    return {"success": True, "data": {"message": "Knowledge base purged"}, "error": None}


@router.get("/executions")
async def list_executions(
    limit: int = Query(20, ge=1, le=100),
    agent_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    q = select(AgentExecution).order_by(AgentExecution.created_at.desc()).limit(limit)
    if agent_name:
        q = q.where(AgentExecution.agent_name == agent_name)
    rows = (await db.execute(q)).scalars().all()
    return {"success": True, "data": [
        {"id": r.id, "agent_name": r.agent_name, "status": r.status,
         "latency_ms": r.latency_ms, "est_cost_usd": r.est_cost_usd,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ], "error": None}


@router.post("/test-pipeline")
async def test_pipeline(
    body: dict,
    token: TokenData = Security(get_current_user, scopes=["agents:exec"]),
):
    """Dry-run pipeline — no DB write."""
    logger.info("Pipeline dry-run requested by %s", token.sub)
    from app.services.ai_pipeline import run_pipeline_async, run_pipeline_fallback
    if settings.OLLAMA_MODEL:
        result = await run_pipeline_async("TEST", body, None)
    else:
        result = await run_pipeline_fallback("TEST", body, None)
    logger.info("Pipeline dry-run completed by %s generation=%s", token.sub, result.get("frameworks_used", {}).get("generation"))
    return {"success": True, "data": result, "error": None}
