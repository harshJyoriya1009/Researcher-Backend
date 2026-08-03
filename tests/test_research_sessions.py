import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient) -> dict:
    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Session Tester", "email": "sessions@example.com", "password": "StrongPass1"},
    )
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_list_rename_delete_session(client: AsyncClient):
    headers = await _authed_headers(client)

    create_r = await client.post("/api/v1/research/session", json={}, headers=headers)
    assert create_r.status_code == 201
    session_id = create_r.json()["id"]
    assert create_r.json()["title"] == "New research chat"

    history_r = await client.get("/api/v1/research/history", headers=headers)
    assert history_r.status_code == 200
    assert any(s["id"] == session_id for s in history_r.json()["items"])

    rename_r = await client.patch(
        f"/api/v1/research/session/{session_id}",
        json={"title": "Renamed session"},
        headers=headers,
    )
    assert rename_r.status_code == 200
    assert rename_r.json()["title"] == "Renamed session"

    detail_r = await client.get(f"/api/v1/research/session/{session_id}", headers=headers)
    assert detail_r.status_code == 200
    assert detail_r.json()["session"]["title"] == "Renamed session"
    assert detail_r.json()["messages"] == []

    delete_r = await client.delete(f"/api/v1/research/session/{session_id}", headers=headers)
    assert delete_r.status_code == 204

    missing_r = await client.get(f"/api/v1/research/session/{session_id}", headers=headers)
    assert missing_r.status_code == 404


async def test_session_isolation_between_users(client: AsyncClient):
    headers_a = await _authed_headers(client)

    r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Other User", "email": "other@example.com", "password": "StrongPass1"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

    create_r = await client.post("/api/v1/research/session", json={}, headers=headers_a)
    session_id = create_r.json()["id"]

    # User B should not be able to see user A's session.
    detail_r = await client.get(f"/api/v1/research/session/{session_id}", headers=headers_b)
    assert detail_r.status_code == 404


async def test_models_endpoint(client: AsyncClient):
    headers = await _authed_headers(client)
    r = await client.get("/api/v1/models", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["models"]) > 0
    assert body["current_model"]
    assert all("configured" in m for m in body["models"])


async def test_models_reflect_configured_providers(client: AsyncClient, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    headers = await _authed_headers(client)
    r = await client.get("/api/v1/models", headers=headers)
    body = r.json()

    by_provider = {m["provider"]: m["configured"] for m in body["models"]}
    assert by_provider["openai"] is True
    assert by_provider["groq"] is False
    assert by_provider["gemini"] is False


async def test_history_is_paginated(client: AsyncClient):
    headers = await _authed_headers(client)

    for i in range(5):
        create_r = await client.post(
            "/api/v1/research/session",
            json={"title": f"Session {i + 1}"},
            headers=headers,
        )
        assert create_r.status_code == 201

    page1_r = await client.get("/api/v1/research/history?page=1&page_size=2", headers=headers)
    assert page1_r.status_code == 200
    page1 = page1_r.json()
    assert page1["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert page1["has_more"] is True
    assert len(page1["items"]) == 2

    page2_r = await client.get("/api/v1/research/history?page=2&page_size=2", headers=headers)
    page2 = page2_r.json()
    assert page2["total"] == 5
    assert page2["has_more"] is True
    assert len(page2["items"]) == 2

    page3_r = await client.get("/api/v1/research/history?page=3&page_size=2", headers=headers)
    page3 = page3_r.json()
    assert page3["total"] == 5
    assert page3["has_more"] is False
    assert len(page3["items"]) == 1
