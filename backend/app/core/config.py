"""NEXUS SDLC - Application Configuration"""

import logging
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from typing import List, Optional
import secrets

logger = logging.getLogger("nexus.config")


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────
    APP_NAME: str = "NEXUS SDLC"
    VERSION: str = "1.0.0"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./nexus.db"

    # ── Security / JWT ───────────────────────────────────────
    SECRET_KEY: str = secrets.token_urlsafe(64)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── OAuth2 (Google example — override via .env) ───────────
    OAUTH_GOOGLE_CLIENT_ID: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OAUTH_GOOGLE_CLIENT_ID", "OAUTH2_GOOGLE_CLIENT_ID"),
    )
    OAUTH_GOOGLE_CLIENT_SECRET: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OAUTH_GOOGLE_CLIENT_SECRET", "OAUTH2_GOOGLE_CLIENT_SECRET"),
    )
    OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/auth/callback",
        validation_alias=AliasChoices("OAUTH_REDIRECT_URI", "OAUTH2_REDIRECT_URI"),
    )
    FRONTEND_URL: str = "http://localhost:5173"

    # ── CORS & Hosts ─────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "*.nexus.internal"]

    # ── Rate Limiting ─────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_BURST: int = 20
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10   # stricter for login/register
    RATE_LIMIT_AI_PER_MINUTE: int = 20

    # ── LLM / AI ─────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "phi3:mini"
    LLM_MODEL: str = "phi3:mini"
    CODE_QUALITY_MODEL: str = "mistral:latest"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2000
    AI_GUARDRAILS_ENABLED: bool = True
    AI_INPUT_MAX_CHARS: int = 10_000
    AI_OUTPUT_MAX_CHARS: int = 2_500
    OLLAMA_REQUEST_TIMEOUT_SECONDS: int = 20
    AI_PIPELINE_MAX_SECONDS: int = 45
    AUTOGEN_CODE_MAX_CHARS: int = 4000
    AUTOGEN_MAX_ROUNDS: int = 2
    GMAIL_CLIENT_SECRETS_FILE: Optional[str] = None
    GMAIL_TOKEN_FILE: Optional[str] = None
    GMAIL_IT_MAILBOX: Optional[str] = None
    GMAIL_QUERY: str = "is:unread"
    GMAIL_SYNC_MAX_MESSAGES: int = 10

    # ── LangSmith ────────────────────────────────────────────
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "nexus-sdlc"
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: Optional[str] = None

    # ── ChromaDB ─────────────────────────────────────────────
    CHROMADB_PATH: str = "./chroma_db"
    CHROMADB_COLLECTION: str = "nexus_knowledge_base"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    RAG_TOP_K: int = 3
    RAG_RELEVANCE_THRESHOLD: float = 0.4
    RAG_SEARCH_MODE: str = "hybrid"
    RAG_SEMANTIC_WEIGHT: float = 0.65
    RAG_BM25_WEIGHT: float = 0.35
    RAG_CANDIDATE_POOL: int = 25

    # ── SLA Defaults ─────────────────────────────────────────
    SLA_MATRIX: dict = {
        "Critical": {"Access": 2,  "Issue": 1,  "Information": 4,  "Change": 8,  "Other": 4},
        "High":     {"Access": 8,  "Issue": 4,  "Information": 8,  "Change": 24, "Other": 8},
        "Medium":   {"Access": 24, "Issue": 16, "Information": 24, "Change": 48, "Other": 24},
        "Low":      {"Access": 48, "Issue": 32, "Information": 48, "Change": 96, "Other": 48},
    }

    # ── Bcrypt ───────────────────────────────────────────────
    BCRYPT_ROUNDS: int = 12

    # ── Misc ─────────────────────────────────────────────────
    AI_CONFIDENCE_REVIEW_THRESHOLD: float = 0.7
    QUALITY_SCORE_RETRY_THRESHOLD: float = 60.0
    MAX_QUALITY_RETRIES: int = 1
    FIRST_ADMIN_EMAIL: str = "admin@nexus.local"
    FIRST_ADMIN_PASSWORD: str = "ChangeMe@Admin2024!"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE_PATH: str = "./logs/nexus_backend.log"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
