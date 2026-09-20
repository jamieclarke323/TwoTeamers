from datetime import timedelta
import sqlite3

from app.db import get_db, init_db


def test_signup_creates_account_and_logs_user_in(client, app):
    response = client.post(
        "/signup",
        data={
            "email": "fan@example.com",
            "password": "football123",
            "supported_team": "Arsenal",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT email, supported_team FROM users").fetchone()
        assert user["email"] == "fan@example.com"
        assert user["supported_team"] == "Arsenal"


def test_login_rejects_wrong_password(client):
    client.post(
        "/signup",
        data={
            "email": "fan@example.com",
            "password": "football123",
            "supported_team": "Neutral",
        },
    )
    client.post("/logout")
    response = client.post("/login", data={"email": "fan@example.com", "password": "wrong-pass"})
    assert b"incorrect" in response.data


def test_session_is_remembered_for_thirty_days(app):
    assert app.permanent_session_lifetime == timedelta(days=30)


def test_signup_rejects_unknown_supported_team(client):
    response = client.post(
        "/signup",
        data={
            "email": "fan@example.com",
            "password": "football123",
            "supported_team": "Made Up FC",
        },
    )
    assert b"Choose the team you support" in response.data


def test_signup_lists_neutral_first_then_all_92_clubs(client):
    response = client.get("/signup")
    options = response.data.split(b'<select name="supported_team"', 1)[1].split(
        b"</select>", 1
    )[0]
    assert options.count(b"<option") == 93
    assert options.find(b'value="Neutral"') < options.find(b'value="Arsenal"')


def test_profile_updates_supported_team(signed_in_client, app):
    response = signed_in_client.post(
        "/profile", data={"supported_team": "Charlton Athletic"}
    )
    assert response.status_code == 302
    with app.app_context():
        user = get_db().execute("SELECT supported_team FROM users").fetchone()
        assert user["supported_team"] == "Charlton Athletic"

    profile = signed_in_client.get("/profile")
    assert b'value="Charlton Athletic" selected' in profile.data


def test_profile_rejects_unknown_supported_team(signed_in_client, app):
    response = signed_in_client.post(
        "/profile", data={"supported_team": "Made Up FC"}
    )
    assert b"Choose a valid team" in response.data
    with app.app_context():
        user = get_db().execute("SELECT supported_team FROM users").fetchone()
        assert user["supported_team"] == "Neutral"


def test_existing_database_is_migrated_with_neutral_default(app):
    legacy_path = app.config["DATABASE"] + ".legacy"
    connection = sqlite3.connect(legacy_path)
    connection.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT)"
    )
    connection.execute(
        "INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'hash')"
    )
    connection.commit()
    connection.close()

    app.config["DATABASE"] = legacy_path
    init_db(app)
    connection = sqlite3.connect(legacy_path)
    supported_team = connection.execute(
        "SELECT supported_team FROM users WHERE email = 'old@example.com'"
    ).fetchone()[0]
    connection.close()
    assert supported_team == "Neutral"
