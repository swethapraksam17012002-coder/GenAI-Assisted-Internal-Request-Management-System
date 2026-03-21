"""
NEXUS SDLC - Async Test Suite
Tests: authentication, requests CRUD, code quality, and security basics.
"""

import pytest

from tests.conftest import register_and_login


async def _get_token(client, db_session, scopes: str = "read write agents:exec rag:admin") -> str:
    return await register_and_login(client, db_session, scopes=scopes)


SAMPLE_REQUEST = {
    "requestor_name": "Alice Smith",
    "requestor_email": "alice@corp.com",
    "request_type": "Access",
    "source_channel": "Portal",
    "priority": "High",
    "raw_description": "I need access to the production AWS console to deploy hotfix for incident #4521.",
}


@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "user@nexus.com", "full_name": "A User", "password": "Secure@99!"},
    )
    assert resp.status_code == 201
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_register_duplicate(client):
    data = {"email": "dup@nexus.com", "full_name": "Dup", "password": "Dup@1234!"}
    await client.post("/api/auth/register", json=data)
    resp = await client.post("/api/auth/register", json=data)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "weak@nexus.com", "full_name": "Weak", "password": "weak"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post(
        "/api/auth/register",
        json={"email": "login@nexus.com", "full_name": "L User", "password": "Login@1234!"},
    )
    resp = await client.post(
        "/api/auth/token",
        data={"username": "login@nexus.com", "password": "Login@1234!", "grant_type": "password"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/api/auth/register",
        json={"email": "bad@nexus.com", "full_name": "Bad", "password": "Good@1234!"},
    )
    resp = await client.post(
        "/api/auth/token",
        data={"username": "bad@nexus.com", "password": "wrong", "grant_type": "password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client, db_session):
    token = await _get_token(client, db_session)
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "test@nexus.com"


@pytest.mark.asyncio
async def test_me_unauthenticated(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client):
    await client.post(
        "/api/auth/register",
        json={"email": "refresh@nexus.com", "full_name": "R", "password": "Refresh@1!"},
    )
    tokens = (
        await client.post(
            "/api/auth/token",
            data={"username": "refresh@nexus.com", "password": "Refresh@1!", "grant_type": "password"},
        )
    ).json()
    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    resp2 = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_create_request(client, db_session):
    token = await _get_token(client, db_session)
    resp = await client.post(
        "/api/requests/",
        json=SAMPLE_REQUEST,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["request"]["id"].startswith("REQ-")
    assert data["request"]["status"] == "Draft"


@pytest.mark.asyncio
async def test_create_request_validation_fail(client, db_session):
    token = await _get_token(client, db_session)
    bad = {**SAMPLE_REQUEST, "priority": "SuperHigh"}
    resp = await client.post("/api/requests/", json=bad, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_request(client, db_session):
    token = await _get_token(client, db_session)
    create = await client.post("/api/requests/", json=SAMPLE_REQUEST, headers={"Authorization": f"Bearer {token}"})
    req_id = create.json()["data"]["request"]["id"]

    resp = await client.get(f"/api/requests/{req_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == req_id


@pytest.mark.asyncio
async def test_list_requests(client, db_session):
    token = await _get_token(client, db_session)
    await client.post("/api/requests/", json=SAMPLE_REQUEST, headers={"Authorization": f"Bearer {token}"})
    resp = await client.get("/api/requests/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] >= 1


@pytest.mark.asyncio
async def test_workflow_review_approve(client, db_session):
    token = await _get_token(client, db_session)
    create = await client.post("/api/requests/", json=SAMPLE_REQUEST, headers={"Authorization": f"Bearer {token}"})
    req_id = create.json()["data"]["request"]["id"]

    review = await client.post(
        f"/api/requests/{req_id}/review",
        json={"performed_by": "manager@corp.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert review.status_code == 200
    assert review.json()["data"]["status"] == "Reviewed"

    approve = await client.post(
        f"/api/requests/{req_id}/approve",
        json={"performed_by": "director@corp.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approve.status_code == 200
    assert approve.json()["data"]["status"] == "Approved"


@pytest.mark.asyncio
async def test_approved_request_immutable(client, db_session):
    token = await _get_token(client, db_session)
    create = await client.post("/api/requests/", json=SAMPLE_REQUEST, headers={"Authorization": f"Bearer {token}"})
    req_id = create.json()["data"]["request"]["id"]
    await client.post(
        f"/api/requests/{req_id}/review",
        json={"performed_by": "mgr"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        f"/api/requests/{req_id}/approve",
        json={"performed_by": "dir"},
        headers={"Authorization": f"Bearer {token}"},
    )

    patch = await client.patch(
        f"/api/requests/{req_id}",
        json={"ai_summary": "Attempt to modify"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch.status_code == 403


@pytest.mark.asyncio
async def test_code_quality_clean(client, db_session):
    token = await _get_token(client, db_session)
    clean_code = """
def add(a: int, b: int) -> int:
    \"\"\"Add two integers and return their sum.\"\"\"
    try:
        return a + b
    except TypeError as e:
        raise ValueError(f"Invalid input: {e}")
"""
    resp = await client.post(
        "/api/agents/code-quality",
        json={"code": clean_code, "language": "python"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "summary" in data
    assert data["summary"]["grade"] in list("ABCDF")


@pytest.mark.asyncio
async def test_code_quality_detects_hardcoded_creds(client, db_session):
    token = await _get_token(client, db_session)
    bad_code = 'api_key = "sk-prod-abc1234567890"\npassword = "SuperSecret123"'
    resp = await client.post(
        "/api/agents/code-quality",
        json={"code": bad_code, "language": "python"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    cq001 = next((r for r in results if r["id"] == "CQ-001"), None)
    assert cq001 is not None
    assert cq001["status"] == "FAIL"


@pytest.mark.asyncio
async def test_security_headers_present(client):
    resp = await client.get("/health")
    assert "x-content-type-options" in resp.headers
    assert "x-frame-options" in resp.headers
    assert resp.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_no_scope_access_denied(client, db_session):
    token = await _get_token(client, db_session, scopes="read")
    resp = await client.post(
        "/api/agents/code-quality",
        json={"code": "x=1", "language": "python"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_no_auth(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_no_token(client):
    resp = await client.get("/api/requests/")
    assert resp.status_code == 401
