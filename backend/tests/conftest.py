import os
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


TEST_DB_PATH = Path(__file__).resolve().parent / "test_suite.db"

os.environ["DEBUG"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = ""
os.environ["LLM_MODEL"] = ""
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["RATE_LIMIT_AUTH_PER_MINUTE"] = "10000"
os.environ["RATE_LIMIT_AI_PER_MINUTE"] = "10000"

from app.core.database import Base, get_db
from app.main import app
from app.models.user_model import User
from app.services import rag_service


test_engine = create_async_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _test_get_stats():
    return {"available": False}


async def _test_retrieve_similar(query: str, top_k: int = 3, filter_meta: dict | None = None):
    return []


rag_service.get_stats = _test_get_stats
rag_service.retrieve_similar = _test_retrieve_similar


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


async def register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    email: str = "test@nexus.com",
    full_name: str = "Test User",
    password: str = "Test@1234!",
    scopes: str = "read write agents:exec rag:admin",
) -> str:
    register_resp = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "full_name": full_name,
            "password": password,
        },
    )
    assert register_resp.status_code in {201, 409}, register_resp.text

    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    user.scopes = scopes
    await db_session.commit()

    token_resp = await client.post(
        "/api/auth/token",
        data={
            "username": email,
            "password": password,
            "grant_type": "password",
            "scope": scopes,
        },
    )
    assert token_resp.status_code == 200, token_resp.text
    return token_resp.json()["access_token"]
