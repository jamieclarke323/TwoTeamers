from datetime import timedelta
import sqlite3

from app.db import get_db, get_progress, init_db, save_progress
from test_offline import offline_app, offline_client


def _create_push_test_account(client, team="Home", email="fan@example.com"):
    assert client.post("/signup", data={
        "email": email,
        "password": "football123",
        "supported_team": team,
    }).status_code == 302


def _push_csrf_headers(client):
    client.get("/profile")
    with client.session_transaction() as browser_session:
        return {"X-CSRF-Token": browser_session["push_csrf_token"]}


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


def test_new_account_starts_with_both_notification_categories_disabled(
    offline_client, offline_app
):
    _create_push_test_account(offline_client)
    with offline_app.app_context():
        preferences = get_db().execute(
            """SELECT daily_game_notifications, my_team_notifications,
                      push_preferences_initialized FROM users"""
        ).fetchone()
    assert tuple(preferences) == (0, 0, 0)


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


def test_push_subscription_requires_login(offline_client):
    response = offline_client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
    )
    assert response.status_code == 302
    assert response.location.endswith("/login?next=/push/subscribe")


def _configure_vapid(app, tmp_path):
    private_key_file = tmp_path / "vapid-private.pem"
    private_key_file.write_text("test-private-key", encoding="utf-8")
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = str(private_key_file)


def test_profile_offers_notification_categories_when_push_is_configured(
    offline_client, offline_app, tmp_path
):
    _configure_vapid(offline_app, tmp_path)
    _create_push_test_account(offline_client)
    response = offline_client.get("/profile")
    assert b'id="push-toggle"' in response.data
    assert b"Daily Game Notifications" in response.data
    assert b"My Team Notifications" in response.data
    assert b"Preferences updated" in response.data
    assert b"data-push-configured=\"true\"" in response.data


def test_push_subscription_is_saved_and_can_be_removed(
    offline_client, offline_app, tmp_path
):
    _configure_vapid(offline_app, tmp_path)
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
        "keys": {"p256dh": "public", "auth": "secret"},
    }
    assert offline_client.post(
        "/push/subscribe", json=subscription
    ).status_code == 403
    saved = offline_client.post(
        "/push/subscribe", json=subscription, headers=csrf_headers
    )
    assert saved.status_code == 200
    assert saved.get_json() == {
        "status": "subscribed",
        "daily_game_notifications": True,
        "my_team_notifications": True,
    }
    with offline_app.app_context():
        row = get_db().execute(
            "SELECT user_id FROM push_subscriptions WHERE endpoint = ?",
            (subscription["endpoint"],),
        ).fetchone()
        user = get_db().execute("SELECT id FROM users").fetchone()
        assert row["user_id"] == user["id"]

    assert offline_client.post(
        "/push/unsubscribe", json={"endpoint": subscription["endpoint"]}
    ).status_code == 403
    removed = offline_client.post(
        "/push/unsubscribe",
        json={"endpoint": subscription["endpoint"]},
        headers=csrf_headers,
    )
    assert removed.status_code == 200
    with offline_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_push_subscription_rejects_untrusted_endpoint(
    offline_client, offline_app, tmp_path
):
    _configure_vapid(offline_app, tmp_path)
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    for endpoint in ("https://127.0.0.1/admin", "https://[invalid"):
        response = offline_client.post(
            "/push/subscribe",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "public", "auth": "secret"},
            },
            headers=csrf_headers,
        )
        assert response.status_code == 400


def test_push_subscription_requires_vapid_configuration(offline_client):
    _create_push_test_account(offline_client)
    response = offline_client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
    )
    assert response.status_code == 503


def test_existing_database_migration_enables_both_preferences_for_subscribers(offline_app):
    legacy_path = offline_app.config["DATABASE"] + ".legacy"
    connection = sqlite3.connect(legacy_path)
    connection.execute(
        """CREATE TABLE users (
             id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT,
             supported_team TEXT NOT NULL DEFAULT 'Neutral'
           )"""
    )
    connection.execute(
        "INSERT INTO users (id, email, password_hash) VALUES (1, 'old@example.com', 'hash')"
    )
    connection.execute(
        """CREATE TABLE push_subscriptions (
             endpoint TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
             subscription_json TEXT NOT NULL
           )"""
    )
    connection.execute(
        "INSERT INTO push_subscriptions VALUES (?, ?, ?)",
        ("https://fcm.googleapis.com/fcm/send/legacy", 1, "{}"),
    )
    connection.commit()
    connection.close()

    offline_app.config["DATABASE"] = legacy_path
    init_db(offline_app)
    connection = sqlite3.connect(legacy_path)
    migrated_user = connection.execute(
        """SELECT supported_team, daily_game_notifications,
                  my_team_notifications, push_preferences_initialized
           FROM users WHERE email = 'old@example.com'"""
    ).fetchone()
    connection.close()
    assert migrated_user == ("Neutral", 1, 1, 1)


def test_push_api_requires_csrf_and_preferences_persist_for_both_categories(
    offline_client, offline_app
):
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    response = offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": False, "my_team_notifications": True},
    )
    assert response.status_code == 403

    updated = offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": False, "my_team_notifications": True},
        headers=csrf_headers,
    )
    assert updated.status_code == 200
    assert updated.get_json() == {
        "status": "updated",
        "daily_game_notifications": False,
        "my_team_notifications": True,
    }
    with offline_app.app_context():
        preferences = get_db().execute(
            """SELECT daily_game_notifications, my_team_notifications,
                      push_preferences_initialized
               FROM users"""
        ).fetchone()
        assert tuple(preferences) == (0, 1, 1)


def test_push_preferences_reject_non_boolean_values(offline_client):
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    response = offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": 1, "my_team_notifications": True},
        headers=csrf_headers,
    )
    assert response.status_code == 400


def test_resubscription_does_not_override_saved_preferences(
    offline_client, offline_app, tmp_path
):
    _configure_vapid(offline_app, tmp_path)
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/persistent-preferences",
        "keys": {"p256dh": "public", "auth": "secret"},
    }
    initial = offline_client.post(
        "/push/subscribe", json=subscription, headers=csrf_headers
    )
    assert initial.get_json()["daily_game_notifications"] is True
    assert initial.get_json()["my_team_notifications"] is True

    updated = offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": False, "my_team_notifications": False},
        headers=csrf_headers,
    )
    assert updated.status_code == 200
    resubscribed = offline_client.post(
        "/push/subscribe", json=subscription, headers=csrf_headers
    )
    assert resubscribed.get_json()["daily_game_notifications"] is False
    assert resubscribed.get_json()["my_team_notifications"] is False


def test_user_cannot_remove_another_accounts_subscription(
    offline_client, offline_app, tmp_path
):
    _configure_vapid(offline_app, tmp_path)
    _create_push_test_account(offline_client)
    csrf_headers = _push_csrf_headers(offline_client)
    endpoint = "https://fcm.googleapis.com/fcm/send/owned-device"
    subscription = {
        "endpoint": endpoint,
        "keys": {"p256dh": "public", "auth": "secret"},
    }
    assert offline_client.post(
        "/push/subscribe", json=subscription, headers=csrf_headers
    ).status_code == 200

    other_client = offline_app.test_client()
    assert other_client.post("/signup", data={
        "email": "other@example.com",
        "password": "football123",
        "supported_team": "Neutral",
    }).status_code == 302
    other_client.get("/profile")
    with other_client.session_transaction() as browser_session:
        other_csrf = browser_session["push_csrf_token"]
    response = other_client.post(
        "/push/unsubscribe",
        json={"endpoint": endpoint},
        headers={"X-CSRF-Token": other_csrf},
    )
    assert response.status_code == 200
    with offline_app.app_context():
        subscription_owner = get_db().execute(
            "SELECT user_id FROM push_subscriptions WHERE endpoint = ?",
            (endpoint,),
        ).fetchone()
        assert subscription_owner["user_id"] == 1


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
