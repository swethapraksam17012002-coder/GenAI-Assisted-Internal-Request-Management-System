"""
NEXUS SDLC - Authentication Router
Endpoints: register, login (token), refresh, logout, me, OAuth2 callback
"""

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timezone
import uuid
import logging

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_token_pair,
    refresh_access_token, revoke_token, get_current_user,
    TokenData, TokenPair, generate_csrf_token,
)
from app.models.user_model import User
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger("nexus.auth")


# ── Schemas ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    employee_id: str | None = None
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        errors = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not any(c.isupper() for c in v):
            errors.append("one uppercase letter")
        if not any(c.isdigit() for c in v):
            errors.append("one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in v):
            errors.append("one special character")
        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")
        return v


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    employee_id: str | None
    scopes: list[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _generate_employee_id(db: AsyncSession) -> str:
    """Generate a unique employee ID for newly created users."""
    while True:
        candidate = f"EMP-{uuid.uuid4().hex[:8].upper()}"
        result = await db.execute(select(User.id).where(User.employee_id == candidate))
        if result.scalar_one_or_none() is None:
            return candidate


def _check_account_locked(user: User):
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        delta = int((user.locked_until - datetime.now(timezone.utc)).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked. Try again in {delta} seconds.",
        )


def _oauth_is_configured() -> bool:
    return bool(settings.OAUTH_GOOGLE_CLIENT_ID and settings.OAUTH_GOOGLE_CLIENT_SECRET)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=dict, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new local user account."""
    existing = await _get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        full_name=body.full_name,
        employee_id=await _generate_employee_id(db),
        hashed_password=hash_password(body.password),
        scopes="read write",
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()
    logger.info(f"New user registered: {body.email}")
    return {"success": True, "data": {"user_id": user.id, "email": user.email}, "error": None}


@router.post("/token", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    OAuth2 Password Flow — returns access + refresh JWT pair.
    Implements: account lockout after 5 failed attempts (15-minute lockout).
    """
    from datetime import timedelta
    user = await _get_user_by_email(db, form_data.username)

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _check_account_locked(user)

    if not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            logger.warning(f"Account locked due to too many failed attempts: {user.email}")
        await db.flush()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login — reset counters
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    scopes = user.scopes.split() if user.scopes else ["read"]
    # Respect requested scopes if a subset of user's granted scopes
    requested = form_data.scopes
    if requested:
        scopes = [s for s in requested if s in scopes]

    tokens = create_token_pair(user.id, user.email, scopes)
    logger.info(f"User logged in: {user.email}")
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest):
    """Exchange a refresh token for a new token pair (rotates refresh token)."""
    return refresh_access_token(body.refresh_token)


@router.get("/google/login")
async def google_login():
    """Redirect the browser to Google OAuth."""
    if not _oauth_is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    state = generate_csrf_token()
    params = {
        "client_id": settings.OAUTH_GOOGLE_CLIENT_ID,
        "redirect_uri": settings.OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    response = RedirectResponse(
        url=f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}",
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=600,
    )
    return response


@router.get("/callback")
async def oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Finish Google OAuth, create or update the local user, and redirect to the SPA."""
    if not _oauth_is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.OAUTH_GOOGLE_CLIENT_ID,
                "client_secret": settings.OAUTH_GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.OAUTH_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code >= 400:
            logger.warning("Google token exchange failed: %s", token_resp.text)
            raise HTTPException(status_code=400, detail="Google token exchange failed")

        google_access_token = token_resp.json().get("access_token")
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        if userinfo_resp.status_code >= 400:
            logger.warning("Google userinfo fetch failed: %s", userinfo_resp.text)
            raise HTTPException(status_code=400, detail="Google userinfo fetch failed")

    profile = userinfo_resp.json()
    email = profile.get("email")
    subject = profile.get("sub")
    full_name = profile.get("name") or email
    if not email or not subject:
        raise HTTPException(status_code=400, detail="Google user profile is incomplete")

    user = await _get_user_by_email(db, email)
    now = datetime.now(timezone.utc)
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=full_name,
            employee_id=await _generate_employee_id(db),
            hashed_password=None,
            scopes="read write",
            is_active=True,
            is_verified=True,
            oauth_provider="google",
            oauth_subject=subject,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.oauth_provider = "google"
        user.oauth_subject = subject
        user.is_verified = True
        user.last_login_at = now
        if not user.employee_id:
            user.employee_id = await _generate_employee_id(db)

    await db.flush()

    scopes = user.scopes.split() if user.scopes else ["read"]
    tokens = create_token_pair(user.id, user.email, scopes)
    response = RedirectResponse(
        url=(
            f"{settings.FRONTEND_URL}/login"
            f"#access_token={tokens.access_token}"
            f"&refresh_token={tokens.refresh_token}"
            f"&token_type={tokens.token_type}"
        ),
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie("oauth_state")
    return response


@router.post("/logout")
async def logout(
    request: Request,
    token_data: TokenData = Depends(get_current_user),
):
    """Revoke current access token (adds JTI to blacklist)."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    revoke_token(token)
    return {"success": True, "data": {"message": "Logged out successfully"}, "error": None}


@router.get("/me", response_model=dict)
async def get_me(
    token_data: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return authenticated user profile."""
    result = await db.execute(select(User).where(User.id == token_data.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "success": True,
        "data": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "employee_id": user.employee_id,
            "scopes": token_data.scopes,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "error": None,
    }


@router.get("/csrf-token")
async def get_csrf_token(response: Response):
    """Generate and set a CSRF token cookie for SPA usage."""
    token = generate_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,     # JS-readable for SPA
        samesite="strict",
        secure=False,       # set True in production (HTTPS)
        max_age=3600,
    )
    return {"success": True, "data": {"csrf_token": token}, "error": None}
