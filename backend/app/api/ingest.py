"""External ingestion endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Security
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.core.security import TokenData, get_current_user
from app.services.email_ingestion import gmail_ingestion_ready, sync_gmail_to_requests

router = APIRouter()
logger = logging.getLogger("nexus.ingest")


class GmailSyncRequest(BaseModel):
    max_messages: int | None = None


@router.post("/email/sync")
async def gmail_sync(
    body: GmailSyncRequest,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Security(get_current_user, scopes=["agents:exec"]),
):
    if not gmail_ingestion_ready():
        raise HTTPException(status_code=503, detail="Gmail ingestion is not configured")

    logger.info("Gmail sync requested requester=%s max_messages=%s", token.sub, body.max_messages)
    result = await sync_gmail_to_requests(db, token.sub, max_messages=body.max_messages)
    logger.info(
        "Gmail sync completed requester=%s imported=%s skipped=%s",
        token.sub,
        result.get("imported_count"),
        result.get("skipped_count"),
    )
    return {"success": True, "data": result, "error": None}
