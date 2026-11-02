import pytest

from app import create_app
from app.db import get_db
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("secret", [None, "", "dev-secret-key-change-me", "short"])
def test_production_rejects_missing_or_weak_signing_secret(secret):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"SECRET_KEY": secret, "TESTING": False, "DEVELOPMENT": False})


def test_production_rejects_insecure_session_cookie():
    with pytest.raises(RuntimeError, match="SESSION_COOKIE_SECURE"):
        create_app({
            "SECRET_KEY": "a" * 64, "SESSION_COOKIE_SECURE": False,
            "TESTING": False, "DEVELOPMENT": False,
        })


def _token(client):
    client.get("/")
    with client.session_transaction() as browser_session:
        return browser_session["csrf_token"]


def test_real_csrf_checks_protect_signup_login_profile_logout_and_game(offline_app, offline_client):
    offline_app.config["CSRF_ENABLED"] = True
    account = {"email": "fan@example.com", "password": "football123", "supported_team": "Neutral"}
    assert offline_client.post("/signup", data=account).status_code == 403
    token = _token(offline_client)
    assert offline_client.post("/signup", data={**account, "csrf_token": token}).status_code == 302
    # Authentication clears the old session token.
    assert offline_client.post("/profile", data={"supported_team": "Home", "csrf_token": token}).status_code == 403
    token = _token(offline_client)
    assert offline_client.post("/profile", data={"supported_team": "Home", "csrf_token": token}).status_code == 302
    assert offline_client.post("/quiz/offline-test/guess", json={"guess": "wrong"}).status_code == 403
    assert offline_client.post(
        "/quiz/offline-test/guess", json={"guess": "wrong"}, headers={"X-CSRF-Token": token}
    ).status_code == 200
    assert offline_client.post("/logout").status_code == 403
    assert offline_client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert offline_client.post("/login", data=account).status_code == 403
    token = _token(offline_client)
    assert offline_client.post("/login", data={**account, "csrf_token": token}).status_code == 302


def test_cross_origin_and_fetch_metadata_rejected_even_with_token(offline_app, offline_client):
    offline_app.config["CSRF_ENABLED"] = True
    token = _token(offline_client)
    for headers in [
        {"Origin": "https://evil.example", "X-CSRF-Token": token},
        {"Sec-Fetch-Site": "cross-site", "X-CSRF-Token": token},
    ]:
        assert offline_client.post("/logout", headers=headers).status_code == 403


def test_signed_offline_sync_remains_usable_with_csrf_enabled(offline_app, offline_client):
    offline_app.config["CSRF_ENABLED"] = True
    token = _token(offline_client)
    response = offline_client.post(
        "/quiz/offline-test/offline-package", headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200
    package = response.get_json()["package"]
    assert offline_client.post(
        "/quiz/offline-test/offline-sync", json={"token": package["token"], "actions": []}
    ).status_code == 200
    assert offline_client.post(
        "/quiz/offline-test/offline-sync", json={"token": "forged", "actions": []}
    ).status_code == 403


def test_security_headers_and_payload_limit(offline_client):
    response = offline_client.get("/login", base_url="https://localhost")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in offline_client.get("/login").headers
    assert offline_client.post("/login", data={"password": "x" * 300000}).status_code == 413


@pytest.mark.parametrize("path", [
    "/instance/two-teamers.sqlite", "/.git/config", "/backup_database.py",
    "/static/../instance/two-teamers.sqlite", "/static/../../.git/config",
])
def test_application_does_not_serve_private_files(offline_client, path):
    assert offline_client.get(path).status_code == 404


def test_passwords_are_hashed_and_old_public_key_cannot_sign_accounts(offline_app, offline_client):
    from flask.sessions import SecureCookieSessionInterface
    from flask import Flask
    assert offline_client.post("/signup", data={
        "email": "hash@example.com", "password": "football123", "supported_team": "Neutral",
    }).status_code == 302
    with offline_app.app_context():
        password_hash = get_db().execute("SELECT password_hash FROM users").fetchone()[0]
        assert password_hash.startswith("scrypt:")
        assert "football123" not in password_hash
    forged_app = Flask("forged")
    forged_app.secret_key = "dev-secret-key-change-me"
    serializer = SecureCookieSessionInterface().get_signing_serializer(forged_app)
    assert serializer is not None
    attacker = offline_app.test_client()
    attacker.set_cookie("session", serializer.dumps({"user_id": 1}))
    assert attacker.get("/profile").status_code == 302


def test_login_rate_limit_is_shared_between_clients_and_expires(offline_app, monkeypatch):
    offline_app.config["AUTH_RATE_LIMIT_ENABLED"] = True
    first, second = offline_app.test_client(), offline_app.test_client()
    now = [100000]
    monkeypatch.setattr("app.security.time.time", lambda: now[0])
    for _ in range(20):
        assert first.post("/login", data={"email": "missing@example.com", "password": "wrong"}).status_code == 200
    response = second.post("/login", data={"email": "missing@example.com", "password": "wrong"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
    with offline_app.app_context():
        keys = [row[0] for row in get_db().execute("SELECT bucket FROM auth_attempts")]
        assert all(len(key) == 64 and "example.com" not in key for key in keys)
    now[0] += 901
    assert second.post("/login", data={"email": "missing@example.com", "password": "wrong"}).status_code == 200


def test_accounts_cannot_read_or_change_each_others_progress(offline_app):
    first, second = offline_app.test_client(), offline_app.test_client()
    for client, email in [(first, "first@example.com"), (second, "second@example.com")]:
        assert client.post("/signup", data={
            "email": email, "password": "football123", "supported_team": "Neutral",
        }).status_code == 302
    first.post("/quiz/offline-test/guess", json={"guess": "Guðmundsson"})
    with offline_app.app_context():
        before = list(get_db().execute(
            "SELECT user_id, solved_json FROM progress ORDER BY user_id"
        ))
    second.post("/quiz/offline-test/reset", json={"user_id": 1})
    with offline_app.app_context():
        first_progress = get_db().execute("SELECT solved_json FROM progress WHERE user_id = 1").fetchone()[0]
    assert first_progress == before[0]["solved_json"]
    page = second.get("/profile").get_data(as_text=True)
    assert "first@example.com" not in page
