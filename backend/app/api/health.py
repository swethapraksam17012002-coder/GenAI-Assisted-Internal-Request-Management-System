"""NEXUS SDLC - Health Check Router"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.services.rag_service import get_stats

logger = logging.getLogger("nexus.health")
router = APIRouter()


@router.get("/health", tags=["System"])
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
        logger.exception("Health check database probe failed")

    rag = await get_stats()
    logger.debug("Health check completed db_ok=%s chromadb_available=%s", db_ok, rag.get("available"))
    return {
        "success": True,
        "data": {
            "status": "healthy" if db_ok else "degraded",
            "db": "ok" if db_ok else "error",
            "chromadb": "ok" if rag.get("available") else "unavailable",
            "llm_api": "configured",
        },
        "error": None,
    }
