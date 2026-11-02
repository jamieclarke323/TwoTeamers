from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app import push_notifications
from app.data_loader import FEATURED_LEAGUE_ID, QUIZ_TIMEZONE
from app.db import get_db
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("status_code", [201, 403, 410])
@pytest.mark.parametrize("pem_format", ["PKCS8", "TraditionalOpenSSL"])
@pytest.mark.parametrize("extra_whitespace", [False, True])
def test_real_webpush_accepts_pem_and_preserves_service_status(
    offline_app, monkeypatch, tmp_path, status_code, pem_format, extra_whitespace
):
    import base64
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import requests

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        getattr(serialization.PrivateFormat, pem_format),
        serialization.NoEncryption(),
    )
    if extra_whitespace:
        pem = b"\n" + pem + b"\n\n"
    private_file = tmp_path / "vapid.pem"
    private_file.write_bytes(pem)
    offline_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = str(private_file)
    browser_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    subscription = {
        "endpoint": "https://web.push.apple.com/test-only",
        "keys": {"p256dh": encode(browser_key), "auth": encode(os.urandom(16))},
    }
    sent_headers = []

    def fake_post(*args, **kwargs):
        sent_headers.append(kwargs["headers"])
        response = requests.Response()
        response.status_code = status_code
        response._content = b""
        return response

    monkeypatch.setattr(requests, "post", fake_post)
    with offline_app.app_context():
        private_key = push_notifications._load_private_key()
        if status_code == 201:
            push_notifications._send_web_push(subscription, {"title": "Test"}, private_key)
        else:
            with pytest.raises(push_notifications.PushDeliveryError) as error:
                push_notifications._send_web_push(
                    subscription, {"title": "Test"}, private_key
                )
            assert error.value.status_code == status_code
    assert len(sent_headers) == 1
    assert sent_headers[0]["Authorization"].startswith("vapid ")
    public_key = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    assert sent_headers[0]["Authorization"].endswith(f"k={encode(public_key)}")
    assert private_file.read_bytes() == pem


def _configure_push_user(client, app, team, tmp_path, device_count=1):
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    private_key_file = tmp_path / "vapid-private.pem"
    private_key_file.write_text("test-private-key", encoding="utf-8")
    app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = str(private_key_file)
    assert client.post("/signup", data={
        "email": "fan@example.com",
        "password": "football123",
        "supported_team": team,
    }).status_code == 302
    client.get("/profile")
    with client.session_transaction() as browser_session:
        csrf_token = browser_session["push_csrf_token"]
    endpoints = []
    for device in range(device_count):
        endpoint = f"https://fcm.googleapis.com/fcm/send/test-token-{device}"
        response = client.post(
            "/push/subscribe",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "public", "auth": f"secret-{device}"},
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200
        endpoints.append(endpoint)
    return endpoints


def _featured_quiz(base, *, quiz_id, day, home=None, away=None):
    return replace(
        base,
        quiz_id=quiz_id,
        league_id=FEATURED_LEAGUE_ID,
        fixture_date=datetime(*day, 15, 0, tzinfo=QUIZ_TIMEZONE),
        home_team=home or base.home_team,
        away_team=away or base.away_team,
    )


def test_daily_game_sends_once_per_device_and_opens_featured_game(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-test-daily", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    endpoints = _configure_push_user(
        offline_client, offline_app, quiz.home_team, tmp_path, device_count=2
    )
    deliveries = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: deliveries.append((subscription, message)),
    )

    assert push_notifications.send_daily_game_notifications(offline_app, now) == 2
    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert len(deliveries) == 2
    assert all(
        message["title"] == "Today's Two Teamers game is ready to play!"
        and message["url"] == "/featured"
        for _, message in deliveries
    )
    with offline_app.app_context():
        records = get_db().execute(
            """SELECT status, endpoint_hash FROM push_notification_deliveries
               WHERE notification_type = 'daily_game'"""
        ).fetchall()
        assert len(records) == len(endpoints)
        assert all(record["status"] == "sent" for record in records)
        assert all(len(record["endpoint_hash"]) == 64 for record in records)


def test_daily_game_requires_opt_in_and_playable_featured_quiz(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-test-daily", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    with offline_client.session_transaction() as browser_session:
        csrf_token = browser_session["push_csrf_token"]
    offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": False, "my_team_notifications": True},
        headers={"X-CSRF-Token": csrf_token},
    )
    deliveries = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda *args: deliveries.append(args),
    )
    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert not deliveries

    offline_app.config["FEATURED_QUIZZES"] = [
        replace(quiz, players=[])
    ]
    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert not deliveries


def test_my_team_notifications_respect_their_separate_preference(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 45, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = replace(
        base,
        quiz_id="regular-my-team-opt-out",
        fixture_date=datetime(2026, 10, 21, 15, 0, tzinfo=QUIZ_TIMEZONE),
    )
    offline_app.config["QUIZZES"] = [quiz]
    offline_app.config["FEATURED_QUIZZES"] = []
    _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    with offline_client.session_transaction() as browser_session:
        csrf_token = browser_session["push_csrf_token"]
    offline_client.post(
        "/push/preferences",
        json={"daily_game_notifications": True, "my_team_notifications": False},
        headers={"X-CSRF-Token": csrf_token},
    )
    deliveries = []
    monkeypatch.setattr(
        push_notifications, "_send_web_push", lambda *args: deliveries.append(args)
    )

    assert push_notifications.send_my_team_notifications(offline_app, now) == 0
    assert not deliveries


def test_my_team_includes_regular_and_featured_fixtures_and_suppresses_daily_match(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 45, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    daily = _featured_quiz(base, quiz_id="featured-daily", day=(2026, 10, 21))
    duplicate_regular = replace(
        base,
        quiz_id="regular-daily-duplicate",
        fixture_date=daily.fixture_date,
        home_team=daily.home_team,
        away_team=daily.away_team,
    )
    extra_regular = replace(
        base,
        quiz_id="regular-extra",
        fixture_date=daily.fixture_date,
        home_team=daily.home_team,
        away_team="Another Club",
    )
    extra_featured = _featured_quiz(
        base,
        quiz_id="featured-extra",
        day=(2026, 10, 21),
        home=daily.home_team,
        away="A Different Club",
    )
    offline_app.config["FEATURED_QUIZZES"] = [daily, extra_featured]
    offline_app.config["QUIZZES"] = [duplicate_regular, extra_regular]
    _configure_push_user(offline_client, offline_app, daily.home_team, tmp_path)
    deliveries = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: deliveries.append(message),
    )

    assert push_notifications.send_my_team_notifications(offline_app, now) == 2
    assert push_notifications.send_my_team_notifications(offline_app, now) == 0
    assert {message["url"] for message in deliveries} == {
        f"/quiz/{extra_regular.quiz_id}",
        f"/quiz/{extra_featured.quiz_id}",
    }
    with offline_app.app_context():
        sent = get_db().execute(
            """SELECT event_key FROM push_notification_deliveries
               WHERE notification_type = 'my_team' AND status = 'sent'"""
        ).fetchall()
        assert {row["event_key"] for row in sent} == {
            extra_regular.quiz_id,
            extra_featured.quiz_id,
        }


@pytest.mark.parametrize(
    ("category", "utc_now", "expected"),
    [
        ("daily_game", datetime(2026, 1, 15, 7, 31, tzinfo=timezone.utc), True),
        ("daily_game", datetime(2026, 7, 15, 6, 31, tzinfo=timezone.utc), True),
        ("daily_game", datetime(2026, 7, 15, 7, 31, tzinfo=timezone.utc), False),
        ("my_team", datetime(2026, 1, 15, 7, 45, tzinfo=timezone.utc), True),
        ("my_team", datetime(2026, 7, 15, 6, 45, tzinfo=timezone.utc), True),
        ("daily_game", datetime(2026, 1, 15, 7, 36, tzinfo=timezone.utc), False),
    ],
)
def test_send_windows_follow_uk_time_and_dst(offline_app, category, utc_now, expected):
    with offline_app.app_context():
        now = push_notifications._normalise_now(utc_now)
        assert push_notifications._in_send_window(category, now) is expected


def test_daily_game_retries_transient_responses_and_records_attempt_count(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-retry", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    attempts = []

    def fail_twice_then_succeed(*args):
        attempts.append(args)
        if len(attempts) < 3:
            raise push_notifications.PushDeliveryError(
                "temporary service failure", 503
            )

    monkeypatch.setattr(push_notifications, "_send_web_push", fail_twice_then_succeed)
    monkeypatch.setattr(push_notifications.time, "sleep", lambda _seconds: None)

    assert push_notifications.send_daily_game_notifications(offline_app, now) == 1
    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert len(attempts) == 3
    with offline_app.app_context():
        record = get_db().execute(
            """SELECT status, attempts, last_status_code
               FROM push_notification_deliveries"""
        ).fetchone()
        assert tuple(record) == ("sent", 3, None)


def test_transient_failures_stop_after_the_bounded_retry_limit(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-retry-exhausted", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    attempts = []

    def always_transient_failure(*args):
        attempts.append(args)
        raise push_notifications.PushDeliveryError("service unavailable", 503)

    monkeypatch.setattr(
        push_notifications, "_send_web_push", always_transient_failure
    )
    monkeypatch.setattr(push_notifications.time, "sleep", lambda _seconds: None)

    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert len(attempts) == push_notifications.MAX_DELIVERY_ATTEMPTS
    with offline_app.app_context():
        record = get_db().execute(
            "SELECT status, attempts FROM push_notification_deliveries"
        ).fetchone()
        assert tuple(record) == ("failed", push_notifications.MAX_DELIVERY_ATTEMPTS)


def test_invalid_subscription_is_removed_and_failure_is_recorded(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-invalid", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    endpoints = _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda *args: (_ for _ in ()).throw(
            push_notifications.PushDeliveryError("gone", 410)
        ),
    )

    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    with offline_app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM push_subscriptions WHERE endpoint = ?",
            (endpoints[0],),
        ).fetchone()[0] == 0
        delivery = get_db().execute(
            "SELECT status, last_status_code FROM push_notification_deliveries"
        ).fetchone()
        assert tuple(delivery) == ("invalid", 410)


def test_stale_in_progress_delivery_becomes_uncertain_without_duplicate_send(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-stale", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    endpoints = _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    with offline_app.app_context():
        db = get_db()
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute(
            """INSERT INTO push_notification_deliveries
               (user_id, notification_type, event_key, endpoint_hash, status,
                attempts, updated_at)
               VALUES (?, 'daily_game', ?, ?, 'sending', 1,
                       datetime('now', '-16 minutes'))""",
            (
                user_id,
                quiz.quiz_id,
                push_notifications._endpoint_hash(endpoints[0]),
            ),
        )
        db.commit()
    deliveries = []
    monkeypatch.setattr(
        push_notifications, "_send_web_push", lambda *args: deliveries.append(args)
    )

    assert push_notifications.send_daily_game_notifications(offline_app, now) == 0
    assert not deliveries
    with offline_app.app_context():
        record = get_db().execute(
            "SELECT status, last_error FROM push_notification_deliveries"
        ).fetchone()
        assert record["status"] == "uncertain"
        assert "did not finish" in record["last_error"]


def test_test_push_is_limited_to_the_selected_account(
    offline_client, offline_app, monkeypatch, tmp_path
):
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    endpoints = _configure_push_user(
        offline_client, offline_app, base.home_team, tmp_path, device_count=2
    )
    delivered = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: delivered.append(
            (subscription, message)
        ),
    )

    assert push_notifications.send_test_notification(offline_app, "FAN@example.com") == (2, 0)
    assert len(delivered) == len(endpoints)
    assert all(message["url"] == "/profile" for _, message in delivered)


def test_scheduled_sender_surfaces_missing_private_key_configuration(
    offline_client, offline_app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 31, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in offline_app.config["QUIZZES"] if quiz.players)
    quiz = _featured_quiz(base, quiz_id="featured-missing-key", day=(2026, 10, 21))
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    _configure_push_user(offline_client, offline_app, quiz.home_team, tmp_path)
    offline_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = ""
    monkeypatch.setattr(push_notifications, "_send_web_push", lambda *args: None)

    with pytest.raises(RuntimeError, match="PUSH_VAPID_PRIVATE_KEY_FILE"):
        push_notifications.send_daily_game_notifications(offline_app, now)
