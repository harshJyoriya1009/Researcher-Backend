import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_register_and_login(client: AsyncClient):
    register_payload = {
        "name": "Ada Researcher",
        "email": "ada@example.com",
        "password": "StrongPass1",
    }
    r = await client.post("/api/v1/auth/register", json=register_payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "ada@example.com"
    assert "access_token" in body and "refresh_token" in body

    login_r = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "StrongPass1"},
    )
    assert login_r.status_code == 200
    assert login_r.json()["user"]["name"] == "Ada Researcher"


async def test_duplicate_registration_rejected(client: AsyncClient):
    payload = {"name": "Dup User", "email": "dup@example.com", "password": "StrongPass1"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "already_exists"


async def test_login_with_wrong_password_rejected(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob@example.com", "password": "StrongPass1"},
    )
    r = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "WrongPass1"}
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_credentials"


async def test_protected_route_requires_token(client: AsyncClient):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_protected_route_with_token(client: AsyncClient):
    register_r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Carla", "email": "carla@example.com", "password": "StrongPass1"},
    )
    token = register_r.json()["access_token"]

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "carla@example.com"


async def test_logout_revokes_access_token(client: AsyncClient):
    register_r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Logout Test", "email": "logout@example.com", "password": "StrongPass1"},
    )
    token = register_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_r = await client.get("/api/v1/auth/me", headers=headers)
    assert me_r.status_code == 200

    logout_r = await client.post("/api/v1/auth/logout", headers=headers)
    assert logout_r.status_code == 204

    me_after_r = await client.get("/api/v1/auth/me", headers=headers)
    assert me_after_r.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient):
    register_r = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Logout Refresh Test",
            "email": "logoutrefresh@example.com",
            "password": "StrongPass1",
        },
    )
    access_token = register_r.json()["access_token"]
    refresh_token = register_r.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    await client.post("/api/v1/auth/logout", headers=headers, json={"refresh_token": refresh_token})

    refresh_r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_r.status_code == 401


async def test_refresh_token_rotation_invalidates_old_token(client: AsyncClient):
    register_r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Rotation Test", "email": "rotation@example.com", "password": "StrongPass1"},
    )
    old_refresh_token = register_r.json()["refresh_token"]

    first_refresh_r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert first_refresh_r.status_code == 200

    second_refresh_r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh_token})
    assert second_refresh_r.status_code == 401


async def test_forgot_password_only_sends_mail_for_existing_email(client: AsyncClient, monkeypatch):
    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)

    await client.post(
        "/api/v1/auth/register",
        json={"name": "Reset User", "email": "reset@example.com", "password": "StrongPass1"},
    )

    existing_r = await client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
    missing_r = await client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})

    assert existing_r.status_code == 204
    assert missing_r.status_code == 204
    assert len(captured) == 2  # verification email on register + reset email for existing account
    assert any("reset-password?token=" in body for _, _, body in captured)


async def test_reset_password_updates_password_and_invalidates_old_password(
    client: AsyncClient, monkeypatch
):
    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)

    await client.post(
        "/api/v1/auth/register",
        json={"name": "Reset Flow", "email": "flow@example.com", "password": "StrongPass1"},
    )
    await client.post("/api/v1/auth/forgot-password", json={"email": "flow@example.com"})

    reset_body = next(body for _, _, body in captured if "reset-password?token=" in body)
    token = reset_body.split("token=")[1].split()[0]

    reset_r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "NewStrongPass1"},
    )
    assert reset_r.status_code == 204

    old_login_r = await client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "StrongPass1"},
    )
    assert old_login_r.status_code == 401

    new_login_r = await client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "NewStrongPass1"},
    )
    assert new_login_r.status_code == 200


async def test_reset_password_token_cannot_be_reused(client: AsyncClient, monkeypatch):
    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)

    await client.post(
        "/api/v1/auth/register",
        json={"name": "Reuse Guard", "email": "reuse@example.com", "password": "StrongPass1"},
    )
    await client.post("/api/v1/auth/forgot-password", json={"email": "reuse@example.com"})

    reset_body = next(body for _, _, body in captured if "reset-password?token=" in body)
    token = reset_body.split("token=")[1].split()[0]

    first_r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherStrong1"},
    )
    assert first_r.status_code == 204

    second_r = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "AnotherStrong2"},
    )
    assert second_r.status_code == 401


def _google_payload(*, email: str, sub: str, name: str = "Google User", email_verified: bool = True):
    return {
        "email": email,
        "sub": sub,
        "name": name,
        "given_name": name.split(" ")[0],
        "email_verified": email_verified,
    }


async def test_google_login_creates_account_and_linked_account(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="g1@example.com",
            sub="google-sub-1",
            name="Google One",
        ),
    )

    response = await client.post("/api/v1/auth/google", json={"credential": "token-1"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "g1@example.com"
    assert body["user"]["is_verified"] is True

    linked = await client.get(
        "/api/v1/auth/linked-accounts",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert linked.status_code == 200
    linked_body = linked.json()
    assert linked_body["has_password"] is False
    assert len(linked_body["linked_accounts"]) == 1
    assert linked_body["linked_accounts"][0]["provider"] == "google"


async def test_google_login_links_existing_verified_user(client: AsyncClient, monkeypatch):
    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Verified User", "email": "verified@example.com", "password": "StrongPass1"},
    )
    verify_body = next(body for _, _, body in captured if "verify-email?token=" in body)
    verify_token = verify_body.split("token=")[1].split()[0]
    await client.post("/api/v1/auth/verify-email", json={"token": verify_token})

    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="verified@example.com",
            sub="google-sub-2",
            name="Verified User",
        ),
    )

    response = await client.post("/api/v1/auth/google", json={"credential": "token-2"})
    assert response.status_code == 200, response.text

    linked = await client.get(
        "/api/v1/auth/linked-accounts",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert linked.status_code == 200
    assert linked.json()["has_password"] is True
    assert linked.json()["linked_accounts"][0]["email"] == "verified@example.com"


async def test_google_login_rejects_existing_unverified_user(client: AsyncClient, monkeypatch):
    await client.post(
        "/api/v1/auth/register",
        json={"name": "Pending User", "email": "pending@example.com", "password": "StrongPass1"},
    )

    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="pending@example.com",
            sub="google-sub-3",
            name="Pending User",
        ),
    )

    response = await client.post("/api/v1/auth/google", json={"credential": "token-3"})
    assert response.status_code == 409
    assert response.json()["error"] == "already_exists"


async def test_link_google_account_and_unlink_requires_password(client: AsyncClient, monkeypatch):
    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)
    register_r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Link User", "email": "link@example.com", "password": "StrongPass1"},
    )
    verify_body = next(body for _, _, body in captured if "verify-email?token=" in body)
    verify_token = verify_body.split("token=")[1].split()[0]
    await client.post("/api/v1/auth/verify-email", json={"token": verify_token})
    access_token = register_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="link@example.com",
            sub="google-sub-4",
            name="Link User",
        ),
    )

    link_r = await client.post("/api/v1/auth/link/google", json={"credential": "token-4"}, headers=headers)
    assert link_r.status_code == 204

    linked = await client.get("/api/v1/auth/linked-accounts", headers=headers)
    assert linked.status_code == 200
    assert linked.json()["linked_accounts"][0]["provider"] == "google"

    unlink_r = await client.delete("/api/v1/auth/link/google", headers=headers)
    assert unlink_r.status_code == 204

    linked_after = await client.get("/api/v1/auth/linked-accounts", headers=headers)
    assert linked_after.status_code == 200
    assert linked_after.json()["linked_accounts"] == []


async def test_unlink_google_account_rejected_without_password(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="nopass@example.com",
            sub="google-sub-5",
            name="No Pass",
        ),
    )

    login_r = await client.post("/api/v1/auth/google", json={"credential": "token-5"})
    assert login_r.status_code == 200
    access_token = login_r.json()["access_token"]

    unlink_r = await client.delete(
        "/api/v1/auth/link/google",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert unlink_r.status_code == 422
    assert unlink_r.json()["error"] == "validation_failed"


async def test_google_account_cannot_be_linked_twice(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="first@example.com",
            sub="google-sub-6",
            name="First User",
        ),
    )
    first_login = await client.post("/api/v1/auth/google", json={"credential": "token-6"})
    assert first_login.status_code == 200

    captured: list[tuple[str, str, str]] = []

    async def fake_send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
        captured.append((to, subject, body))

    monkeypatch.setattr("app.services.auth_service.send_email", fake_send_email)
    register_r = await client.post(
        "/api/v1/auth/register",
        json={"name": "Second User", "email": "second@example.com", "password": "StrongPass1"},
    )
    verify_body = next(body for _, _, body in captured if "verify-email?token=" in body)
    verify_token = verify_body.split("token=")[1].split()[0]
    await client.post("/api/v1/auth/verify-email", json={"token": verify_token})

    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="second@example.com",
            sub="google-sub-6",
            name="Second User",
        ),
    )

    link_r = await client.post(
        "/api/v1/auth/link/google",
        json={"credential": "token-7"},
        headers={"Authorization": f"Bearer {register_r.json()['access_token']}"},
    )
    assert link_r.status_code == 409
    assert link_r.json()["error"] == "already_exists"


async def test_password_login_on_google_only_account_shows_google_message(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth_service.verify_google_id_token",
        lambda credential: _google_payload(
            email="googleonly@example.com",
            sub="google-sub-7",
            name="Google Only",
        ),
    )

    login_r = await client.post("/api/v1/auth/google", json={"credential": "token-8"})
    assert login_r.status_code == 200

    password_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "googleonly@example.com", "password": "StrongPass1"},
    )
    assert password_login.status_code == 401
    assert "Google sign-in" in password_login.json()["message"]
