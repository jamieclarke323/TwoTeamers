import re

import pytest
from werkzeug.security import generate_password_hash

from test_offline import offline_app, offline_client


@pytest.fixture
def protected_admin(offline_app):
    offline_app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("test-admin-password")
    return offline_app


@pytest.mark.parametrize("path", ["/admin", "/admin/matchup?team1=Home&team2=Away"])
def test_admin_requires_password_on_both_routes(protected_admin, offline_client, path):
    response = offline_client.get(path)
    assert response.status_code == 200
    assert b"Unlock admin" in response.data
    assert b"Matchup Answer Generator" not in response.data
    assert response.headers["Cache-Control"] == "no-store"
    response = offline_client.post(path, data={"password": "test-admin-password"}, follow_redirects=True)
    assert b"Matchup Answer Generator" in response.data


def test_fifth_failure_locks_for_full_ten_minutes_across_sessions(protected_admin, offline_client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.admin_access.time.time", lambda: now[0])
    for _ in range(4):
        assert offline_client.post("/admin", data={"password": "wrong"}).status_code == 401
    response = offline_client.post("/admin", data={"password": "wrong"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "600"
    another = protected_admin.test_client()
    now[0] += 599
    response = another.post("/admin/matchup", data={"password": "test-admin-password"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"
    now[0] += 1
    assert another.post("/admin", data={"password": "test-admin-password"}).status_code == 302
    assert another.get("/admin").status_code == 200


def test_success_resets_failures_and_grant_expires(protected_admin, offline_client, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.admin_access.time.time", lambda: now[0])
    for _ in range(4):
        offline_client.post("/admin", data={"password": "wrong"})
    assert offline_client.post("/admin", data={"password": "test-admin-password"}).status_code == 302
    now[0] += 3600
    assert b"Unlock admin" in offline_client.get("/admin").data
    assert offline_client.post("/admin", data={"password": "wrong"}).status_code == 401


def test_missing_config_fails_closed(offline_client):
    assert offline_client.get("/admin").status_code == 503


def test_password_change_invalidates_grant(protected_admin, offline_client):
    offline_client.post("/admin", data={"password": "test-admin-password"})
    protected_admin.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("new-test-password")
    assert b"Unlock admin" in offline_client.get("/admin").data


def test_admin_post_requires_csrf(protected_admin, offline_client):
    protected_admin.config["CSRF_ENABLED"] = True
    assert offline_client.post("/admin", data={"password": "test-admin-password"}).status_code == 403
    page = offline_client.get("/admin").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert offline_client.post("/admin", data={
        "password": "test-admin-password", "csrf_token": token,
    }).status_code == 302
