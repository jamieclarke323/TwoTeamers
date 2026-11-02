from datetime import datetime
from unittest.mock import patch

import pytest

from app.data_loader import QUIZ_TIMEZONE, Quiz
from app.db import get_db
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("day, expected_close", [
    (datetime(2026, 3, 29, tzinfo=QUIZ_TIMEZONE), "2026-03-30T00:00:00+01:00"),
    (datetime(2026, 10, 25, tzinfo=QUIZ_TIMEZONE), "2026-10-26T00:00:00+00:00"),
])
@pytest.mark.parametrize("playable_hours", [48, 72, 100])
def test_home_countdowns_use_uk_midnight_and_configured_playable_hours(
    offline_app, offline_client, monkeypatch, day, expected_close, playable_hours
):
    monkeypatch.setattr("app.data_loader.PLAYABLE_HOURS", playable_hours)
    quiz = offline_app.config["QUIZZES"][0]
    quiz.fixture_date = day
    monkeypatch.setattr("app.routes.todays_featured_quiz", lambda: quiz)
    offline_client.post("/signup", data={
        "email": "countdown@example.com", "password": "football123",
        "supported_team": "Home",
    })
    page = offline_client.get("/").get_data(as_text=True)
    daily_panel = page.split('class="home-panel featured-home-panel"', 1)[1].split("</a>", 1)[0]
    team_panel = page.split('class="home-panel your-team-panel"', 1)[1].split("</a>", 1)[0]
    assert f'data-closes-at="{expected_close}"' in daily_panel
    assert f'data-closes-at="{quiz.lock_at.isoformat()}"' in team_panel
    assert page.count("data-closes-at=") == 2


def test_home_countdowns_absent_without_featured_or_playable_team_game(
    offline_app, offline_client, monkeypatch
):
    assert "data-closes-at=" not in offline_client.get("/").get_data(as_text=True)
    offline_client.post("/signup", data={
        "email": "locked@example.com", "password": "football123",
        "supported_team": "Home",
    })
    offline_app.config["BYPASS_AVAILABILITY"] = False
    monkeypatch.setattr(Quiz, "availability", lambda quiz: "upcoming")
    page = offline_client.get("/").get_data(as_text=True)
    assert "Locked" in page
    assert "data-closes-at=" not in page


def test_guest_home_has_four_panels_and_login_toast(client):
    page = client.get('/').data
    assert page.count(b'class="home-panel ') == 4
    assert b'id="guest-your-team"' in page
    assert b'log in to use this button' in page
    assert b'js/home.js' in page


def test_charlton_fan_sees_open_burnley_fixture(signed_in_client, app):
    app.config['BYPASS_AVAILABILITY'] = False
    with app.app_context():
        get_db().execute("UPDATE users SET supported_team = 'Charlton Athletic' WHERE id = 1")
        get_db().commit()
    now = datetime(2026, 10, 13, 12, tzinfo=QUIZ_TIMEZONE)
    availability = Quiz.availability
    with patch.object(Quiz, 'availability', lambda quiz: availability(quiz, now)):
        page = signed_in_client.get('/').data
    panel = page.split(b'class="home-panel your-team-panel"', 1)[1].split(b'</a>', 1)[0]
    assert b'Burnley' in panel and b'Charlton Athletic' in panel
    assert b'Burnley.png' in panel and b'Charlton.png' in panel
    assert b"Play your team's game" in panel


def test_supporter_without_open_fixture_sees_next_unlock(signed_in_client, app):
    app.config['BYPASS_AVAILABILITY'] = False
    with app.app_context():
        get_db().execute("UPDATE users SET supported_team = 'Charlton Athletic' WHERE id = 1")
        get_db().commit()
    now = datetime(2026, 10, 8, 12, tzinfo=QUIZ_TIMEZONE)
    availability = Quiz.availability
    with patch.object(Quiz, 'availability', lambda quiz: availability(quiz, now)):
        page = signed_in_client.get('/').data
    panel = page.split(b'class="home-panel your-team-panel locked-team-panel"', 1)[1].split(b'</a>', 1)[0]
    assert b'Bristol City' in panel
    assert b'Opens 10 October 2026 at 00:00' in panel
    assert b'&#128274;' in panel
