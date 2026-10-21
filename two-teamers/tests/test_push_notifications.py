from dataclasses import replace
from datetime import datetime

from app import push_notifications
from app.data_loader import QUIZ_TIMEZONE
from app.db import get_db


def _configure_push_user(signed_in_client, app, team, tmp_path):
    app.config["PUSH_VAPID_PUBLIC_KEY"] = "public-key"
    private_key_file = tmp_path / "vapid-private.pem"
    private_key_file.write_text("test-private-key", encoding="utf-8")
    app.config["PUSH_VAPID_PRIVATE_KEY_FILE"] = str(private_key_file)
    signed_in_client.post(
        "/profile", data={"supported_team": team}
    )
    response = signed_in_client.post(
        "/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-token",
            "keys": {"p256dh": "public", "auth": "secret"},
        },
    )
    assert response.status_code == 200


def test_sends_once_for_a_supported_team_game_and_opens_that_game(
    signed_in_client, app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 30, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    quiz = replace(
        base,
        fixture_date=datetime(2026, 10, 21, 6, 0, tzinfo=QUIZ_TIMEZONE),
    )
    app.config["QUIZZES"] = [quiz]
    _configure_push_user(signed_in_client, app, quiz.home_team, tmp_path)
    deliveries = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: deliveries.append((subscription, message)),
    )

    assert push_notifications.send_daily_notifications(app, now) == 1
    assert push_notifications.send_daily_notifications(app, now) == 0
    assert len(deliveries) == 1
    assert deliveries[0][1]["title"] == "Today's Two Teamers game is ready to play!"
    assert deliveries[0][1]["url"] == f"/quiz/{quiz.quiz_id}"


def test_does_not_send_before_fixture_unlock(signed_in_client, app, monkeypatch, tmp_path):
    now = datetime(2026, 10, 21, 5, 30, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    quiz = replace(
        base,
        fixture_date=datetime(2026, 10, 21, 8, 0, tzinfo=QUIZ_TIMEZONE),
    )
    app.config["QUIZZES"] = [quiz]
    _configure_push_user(signed_in_client, app, quiz.home_team, tmp_path)
    deliveries = []
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: deliveries.append(message),
    )

    assert push_notifications.send_daily_notifications(app, now) == 0
    assert not deliveries


def test_user_with_no_game_that_day_is_skipped(
    signed_in_client, app, monkeypatch, tmp_path
):
    now = datetime(2026, 10, 21, 7, 30, tzinfo=QUIZ_TIMEZONE)
    base = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    quiz = replace(
        base,
        fixture_date=datetime(2026, 10, 22, 6, 0, tzinfo=QUIZ_TIMEZONE),
    )
    app.config["QUIZZES"] = [quiz]
    _configure_push_user(signed_in_client, app, quiz.home_team, tmp_path)
    monkeypatch.setattr(
        push_notifications,
        "_send_web_push",
        lambda subscription, message, private_key: None,
    )

    assert push_notifications.send_daily_notifications(app, now) == 0
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM push_notification_sends"
        ).fetchone()[0] == 0
