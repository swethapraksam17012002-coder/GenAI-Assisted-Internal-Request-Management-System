"""NEXUS SDLC - Dashboard & Analytics Routers"""

import logging
from fastapi import APIRouter, Depends, Security, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.core.security import get_current_user, TokenData
from app.models.request_model import Request as RequestModel

logger = logging.getLogger("nexus.dashboard")
dashboard_router = APIRouter()
analytics_router = APIRouter()


@dashboard_router.get("/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Dashboard stats requested by %s", token.sub)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total       = (await db.execute(select(func.count()).select_from(RequestModel))).scalar_one()
    open_count  = (await db.execute(select(func.count()).select_from(RequestModel).where(
        RequestModel.status.in_(["Draft","Reviewed","In Progress"])))).scalar_one()
    overdue     = (await db.execute(select(func.count()).select_from(RequestModel).where(
        RequestModel.is_overdue == True))).scalar_one()
    completed_today = (await db.execute(select(func.count()).select_from(RequestModel).where(
        RequestModel.status == "Completed",
        RequestModel.resolved_at >= today_start))).scalar_one()

    on_time_sla = total - overdue if total > 0 else 0
    sla_pct = round((on_time_sla / total) * 100, 1) if total > 0 else 100.0

    avg_conf = (await db.execute(select(func.avg(RequestModel.ai_confidence_score)))).scalar_one()
    avg_ms   = (await db.execute(select(func.avg(RequestModel.agent_processing_ms)))).scalar_one()

    return {"success": True, "data": {
        "total": total, "open": open_count, "overdue": overdue,
        "completed_today": completed_today,
        "sla_compliance_pct": sla_pct,
        "avg_confidence": round(float(avg_conf or 0), 3),
        "avg_processing_ms": int(avg_ms or 0),
    }, "error": None}


@dashboard_router.get("/trend")
async def trend(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Dashboard trend requested by %s for days=%s", token.sub, days)
    now = datetime.now(timezone.utc)
    result = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        count = (await db.execute(
            select(func.count()).select_from(RequestModel).where(
                RequestModel.created_at >= day_start,
                RequestModel.created_at < day_end,
            )
        )).scalar_one()
        result.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})
    return {"success": True, "data": result, "error": None}


@analytics_router.get("/by-status")
async def by_status(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Analytics by-status requested by %s", token.sub)
    rows = (await db.execute(
        select(RequestModel.status, func.count()).group_by(RequestModel.status)
    )).all()
    return {"success": True, "data": {r[0]: r[1] for r in rows}, "error": None}


@analytics_router.get("/by-priority")
async def by_priority(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Analytics by-priority requested by %s", token.sub)
    rows = (await db.execute(
        select(RequestModel.priority, func.count()).group_by(RequestModel.priority)
    )).all()
    return {"success": True, "data": {r[0]: r[1] for r in rows}, "error": None}


@analytics_router.get("/by-type")
async def by_type(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Analytics by-type requested by %s", token.sub)
    rows = (await db.execute(
        select(RequestModel.request_type, func.count()).group_by(RequestModel.request_type)
    )).all()
    return {"success": True, "data": {r[0]: r[1] for r in rows}, "error": None}


@analytics_router.get("/by-channel")
async def by_channel(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("Analytics by-channel requested by %s", token.sub)
    rows = (await db.execute(
        select(RequestModel.source_channel, func.count()).group_by(RequestModel.source_channel)
    )).all()
    return {"success": True, "data": {r[0]: r[1] for r in rows}, "error": None}


@analytics_router.get("/sla")
async def sla_analytics(
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["read"]),
):
    logger.debug("SLA analytics requested by %s", token.sub)
    total    = (await db.execute(select(func.count()).select_from(RequestModel))).scalar_one()
    overdue  = (await db.execute(select(func.count()).select_from(RequestModel).where(
        RequestModel.is_overdue == True))).scalar_one()
    on_time  = total - overdue
    rate     = round((on_time / total) * 100, 1) if total > 0 else 100.0
    return {"success": True, "data": {
        "total": total, "on_time": on_time, "overdue": overdue,
        "compliance_rate_pct": rate,
    }, "error": None}


# Expose both as named exports for main.py
router = dashboard_router   # dashboard_router already named above
