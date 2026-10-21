from datetime import timedelta
import sqlite3

from app.db import get_db, get_progress, init_db, save_progress


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


def test_push_subscription_requires_login(client):
    response = client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
    )
    assert response.status_code == 302
    assert response.location.endswith("/login?next=/push/subscribe")


def test_profile_offers_opt_in_when_push_is_configured(signed_in_client, app):
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    response = signed_in_client.get("/profile")
    assert b'id="push-toggle"' in response.data
    assert b"Opt in to a browser notification at 7:30am UK time" in response.data


def test_push_subscription_is_saved_and_can_be_removed(signed_in_client, app):
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
        "keys": {"p256dh": "public", "auth": "secret"},
    }
    saved = signed_in_client.post("/push/subscribe", json=subscription)
    assert saved.status_code == 200
    assert saved.get_json() == {"status": "subscribed"}
    with app.app_context():
        row = get_db().execute(
            "SELECT user_id FROM push_subscriptions WHERE endpoint = ?",
            (subscription["endpoint"],),
        ).fetchone()
        user = get_db().execute("SELECT id FROM users").fetchone()
        assert row["user_id"] == user["id"]

    removed = signed_in_client.post(
        "/push/unsubscribe", json={"endpoint": subscription["endpoint"]}
    )
    assert removed.status_code == 200
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_push_subscription_rejects_untrusted_endpoint(signed_in_client, app):
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    for endpoint in ("https://127.0.0.1/admin", "https://[invalid"):
        response = signed_in_client.post(
            "/push/subscribe",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "public", "auth": "secret"},
            },
        )
        assert response.status_code == 400


def test_push_subscription_requires_vapid_configuration(signed_in_client):
    response = signed_in_client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
    )
    assert response.status_code == 503


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


def test_guest_progress_moves_into_new_account_on_signup(client, app):
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    guess = client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    )
    assert guess.get_json()["status"] == "correct"
    with client.session_transaction() as browser_session:
        visitor_id = browser_session["visitor_id"]

    response = client.post(
        "/signup",
        data={
            "email": "guest-upgrade@example.com",
            "password": "football123",
            "supported_team": "Arsenal",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user_id = get_db().execute(
            "SELECT id FROM users WHERE email = ?", ("guest-upgrade@example.com",)
        ).fetchone()["id"]
        assert get_progress(user_id, quiz.quiz_id)["solved"] == [0]
        assert get_db().execute(
            "SELECT 1 FROM guest_progress WHERE visitor_id = ?", (visitor_id,)
        ).fetchone() is None


def test_guest_progress_moves_into_existing_account_on_login(client, app):
    client.post(
        "/signup",
        data={
            "email": "existing-fan@example.com",
            "password": "football123",
            "supported_team": "Arsenal",
        },
    )
    client.post("/logout")
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    guess = client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    )
    assert guess.get_json()["status"] == "correct"
    with client.session_transaction() as browser_session:
        visitor_id = browser_session["visitor_id"]

    response = client.post(
        "/login",
        data={"email": "existing-fan@example.com", "password": "football123"},
    )
    assert response.status_code == 302
    with app.app_context():
        user_id = get_db().execute(
            "SELECT id FROM users WHERE email = ?", ("existing-fan@example.com",)
        ).fetchone()["id"]
        assert get_progress(user_id, quiz.quiz_id)["solved"] == [0]
        assert get_db().execute(
            "SELECT 1 FROM guest_progress WHERE visitor_id = ?", (visitor_id,)
        ).fetchone() is None
