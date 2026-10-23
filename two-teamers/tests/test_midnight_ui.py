from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.data_loader import FEATURED_LEAGUE_ID, PLAYABLE_HOURS, QUIZ_TIMEZONE, Quiz
from app.db import get_db
from app import push_notifications
from app.routes import todays_featured_quiz
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("featured", [False, True])
@pytest.mark.parametrize("date", [(2026, 10, 24), (2026, 10, 25), (2026, 3, 29)])
def test_all_games_unlock_at_exact_fixture_day_midnight(offline_app, featured, date):
    quiz = replace(
        offline_app.config["QUIZZES"][0],
        fixture_date=datetime(*date, 15, 0, tzinfo=QUIZ_TIMEZONE),
        league_id=FEATURED_LEAGUE_ID if featured else "championship",
    )
    midnight = datetime(*date, tzinfo=QUIZ_TIMEZONE)
    assert quiz.unlock_at == midnight
    assert quiz.availability(midnight - timedelta(microseconds=1)) == "upcoming"
    assert quiz.availability(midnight) == "playable"
    assert quiz.availability(midnight + timedelta(minutes=1)) == "playable"
    assert quiz.availability(midnight.astimezone(timezone.utc)) == "playable"
    assert quiz.lock_at == midnight + timedelta(hours=PLAYABLE_HOURS)
    assert quiz.availability(quiz.lock_at) == "expired"


def test_featured_selection_switches_at_uk_midnight(offline_app):
    quiz = replace(
        offline_app.config["QUIZZES"][0], league_id=FEATURED_LEAGUE_ID,
        fixture_date=datetime(2026, 10, 24, 15, tzinfo=QUIZ_TIMEZONE),
    )
    offline_app.config["FEATURED_QUIZZES"] = [quiz]
    midnight = quiz.unlock_at
    with offline_app.app_context():
        assert todays_featured_quiz(midnight - timedelta(microseconds=1)) is None
        assert todays_featured_quiz(midnight) is quiz
        assert todays_featured_quiz(midnight.astimezone(timezone.utc)) is quiz


def _sign_in(app, client):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (id,email,password_hash,supported_team) VALUES (1,'fan@example.com','hash','Home')")
        db.commit()
    with client.session_transaction() as browser_session:
        browser_session["user_id"] = 1


def test_home_lock_and_game_guards_change_at_midnight(offline_app, offline_client):
    _sign_in(offline_app, offline_client)
    quiz = replace(offline_app.config["QUIZZES"][0], fixture_date=datetime(2026, 10, 24, 15, tzinfo=QUIZ_TIMEZONE))
    offline_app.config.update(
        QUIZZES=[quiz], QUIZZES_BY_ID={quiz.quiz_id: quiz}, BYPASS_AVAILABILITY=False,
    )
    availability = Quiz.availability
    midnight = quiz.unlock_at
    with patch.object(Quiz, "availability", lambda self: availability(self, midnight - timedelta(seconds=1))):
        page = offline_client.get("/").data
        assert b"your-team-panel locked-team-panel" in page
        assert b"&#128274;" in page
        assert b"Opens 24 October 2026 at 00:00" in page
        assert b"midnight (00:00 UK time)" in offline_client.get(f"/quiz/{quiz.quiz_id}").data
        for action in ("guess", "offline-package"):
            assert offline_client.post(f"/quiz/{quiz.quiz_id}/{action}", json={"guess": "Aanholt"}).status_code == 403
    with patch.object(Quiz, "availability", lambda self: availability(self, midnight)):
        page = offline_client.get("/").data
        assert b"locked-team-panel" not in page
        assert b"Play your team's game" in page
        assert offline_client.post(f"/quiz/{quiz.quiz_id}/guess", json={"guess": "Aanholt"}).json["status"] == "correct"
        assert offline_client.post(f"/quiz/{quiz.quiz_id}/offline-package").status_code == 200


def test_profile_shows_disabled_opt_in_until_keys_configured(offline_app, offline_client):
    _sign_in(offline_app, offline_client)
    offline_app.config["PUSH_VAPID_PUBLIC_KEY"] = ""
    page = offline_client.get("/profile").get_data(as_text=True)
    button = page.split('id="push-toggle"', 1)[1].split("</button>", 1)[0]
    assert "disabled" in button
    assert "Enable notifications" in button
    assert "site owner needs to finish notification setup" in page
    assert "/static/js/push-notifications.js" not in page
    assert offline_client.post("/push/subscribe", json={}).status_code == 503
    offline_app.config["PUSH_VAPID_PUBLIC_KEY"] = "test-public-key"
    page = offline_client.get("/profile").get_data(as_text=True)
    button = page.split('id="push-toggle"', 1)[1].split("</button>", 1)[0]
    assert "disabled" not in button
    assert "test-public-key" in button
    assert "/static/js/push-notifications.js" in page


def test_daily_push_still_sends_at_morning_task_after_midnight_unlock(
    offline_app, offline_client, tmp_path, monkeypatch
):
    _sign_in(offline_app, offline_client)
    quiz = replace(
        offline_app.config["QUIZZES"][0],
        fixture_date=datetime(2026, 10, 24, 15, tzinfo=QUIZ_TIMEZONE),
    )
    private_file = tmp_path / "test-key.pem"
    private_file.write_text("test-only")
    offline_app.config.update(
        QUIZZES=[quiz], PUSH_VAPID_PUBLIC_KEY="public-key",
        PUSH_VAPID_PRIVATE_KEY_FILE=str(private_file),
    )
    assert offline_client.post("/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/midnight-test",
        "keys": {"p256dh": "public", "auth": "auth"},
    }).status_code == 200
    deliveries = []
    monkeypatch.setattr(push_notifications, "_send_web_push", lambda *args: deliveries.append(args))
    assert push_notifications.send_daily_notifications(
        offline_app, quiz.unlock_at - timedelta(seconds=1)
    ) == 0
    morning = quiz.unlock_at.replace(hour=7, minute=30)
    assert push_notifications.send_daily_notifications(offline_app, morning) == 1
    assert push_notifications.send_daily_notifications(offline_app, morning) == 0
    assert len(deliveries) == 1
