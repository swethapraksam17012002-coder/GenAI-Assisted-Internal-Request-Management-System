"""Smoke tests aligned with the current backend routes and modules."""

import pytest

from tests.conftest import register_and_login


async def _auth_headers(client, db_session) -> dict[str, str]:
    token = await register_and_login(
        client,
        db_session,
        email="smoke@nexus.com",
        full_name="Smoke User",
        password="Smoke@1234!",
        scopes="read write agents:exec rag:admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert "x-correlation-id" in resp.headers


@pytest.mark.asyncio
async def test_agent_status_endpoint(client, db_session):
    headers = await _auth_headers(client, db_session)
    resp = await client.get("/api/agents/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "crewai" in data
    assert "autogen" in data


@pytest.mark.asyncio
async def test_request_detail_exposes_pipeline_status(client, db_session):
    headers = await _auth_headers(client, db_session)
    create_resp = await client.post("/api/requests/", json={
        "requestor_name": "John Doe",
        "requestor_email": "john@example.com",
        "request_type": "Access",
        "source_channel": "Portal",
        "priority": "Medium",
        "raw_description": "Please grant VPN access for remote work on my company laptop.",
    }, headers=headers)
    assert create_resp.status_code == 201, create_resp.text
    req_id = create_resp.json()["data"]["request"]["id"]

    detail_resp = await client.get(f"/api/requests/{req_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["id"] == req_id
    assert detail["pipeline_status"] in {"running", "idle"}
