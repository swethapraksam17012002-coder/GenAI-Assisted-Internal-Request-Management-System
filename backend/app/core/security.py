"""
NEXUS SDLC - Security Module
Implements: OAuth2 Password Flow + JWT Access/Refresh Tokens
           Bcrypt password hashing, token blacklisting, scope-based RBAC
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
import secrets

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import logging

from app.core.config import settings

logger = logging.getLogger("nexus.security")

# ── Password hashing ─────────────────────────────────────────────────────────
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.BCRYPT_ROUNDS,
)

# ── OAuth2 scheme ─────────────────────────────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token",
    scopes={
        "read":        "Read requests and dashboard",
        "write":       "Create and update requests",
        "admin":       "Full system access including user management",
        "agents:exec": "Trigger AI agent pipelines",
        "rag:admin":   "Manage RAG knowledge base",
    },
)

# ── Simple in-memory token blacklist (use Redis in production) ────────────────
_token_blacklist: set[str] = set()


# ── Schemas ──────────────────────────────────────────────────────────────────
class TokenData(BaseModel):
    sub: str                          # user id
    email: Optional[str] = None
    scopes: List[str] = []
    jti: Optional[str] = None         # JWT ID for blacklisting
    token_type: str = "access"


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                   # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta, token_type: str = "access") -> str:
    payload = data.copy()
    jti = secrets.token_urlsafe(16)
    payload.update({
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "iss": "nexus-sdlc",
        "jti": jti,
        "type": token_type,
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_token_pair(user_id: str, email: str, scopes: List[str]) -> TokenPair:
    access_exp = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_exp = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    access_payload = {"sub": user_id, "email": email, "scopes": scopes}
    refresh_payload = {"sub": user_id, "email": email, "scopes": scopes}
    return TokenPair(
        access_token=_create_token(access_payload, access_exp, "access"),
        refresh_token=_create_token(refresh_payload, refresh_exp, "refresh"),
        token_type="bearer",
        expires_in=int(access_exp.total_seconds()),
    )


def decode_token(token: str) -> TokenData:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exc

    jti = payload.get("jti")
    if jti and jti in _token_blacklist:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    sub: str = payload.get("sub")
    if not sub:
        raise credentials_exc

    return TokenData(
        sub=sub,
        email=payload.get("email"),
        scopes=payload.get("scopes", []),
        jti=jti,
        token_type=payload.get("type", "access"),
    )


def revoke_token(token: str):
    """Add JTI to blacklist (logout / password change)."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                             options={"verify_exp": False})
        jti = payload.get("jti")
        if jti:
            _token_blacklist.add(jti)
    except JWTError:
        pass


def refresh_access_token(refresh_token: str) -> TokenPair:
    """Exchange a valid refresh token for a new token pair."""
    data = decode_token(refresh_token)
    if data.token_type != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not a refresh token")
    revoke_token(refresh_token)   # rotate: one-time use
    return create_token_pair(data.sub, data.email or "", data.scopes)


# ── Dependency: get current user ─────────────────────────────────────────────
async def get_current_user(
    security_scopes: SecurityScopes,
    token: str = Depends(oauth2_scheme),
) -> TokenData:
    if security_scopes.scopes:
        auth_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        auth_value = "Bearer"

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": auth_value},
    )
    token_data = decode_token(token)
    if token_data.token_type != "access":
        raise credentials_exc

    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required scope: '{scope}'",
                headers={"WWW-Authenticate": auth_value},
            )
    return token_data


async def get_current_admin(token_data: TokenData = Depends(get_current_user)) -> TokenData:
    if "admin" not in token_data.scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return token_data


# ── CSRF protection helper ────────────────────────────────────────────────────
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf_token(request: Request, token: str) -> bool:
    session_token = request.cookies.get("csrf_token")
    if not session_token or not secrets.compare_digest(session_token, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch")
    return True
