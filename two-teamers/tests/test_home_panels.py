from datetime import datetime
from unittest.mock import patch

from app.data_loader import QUIZ_TIMEZONE, Quiz
from app.db import get_db


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
    panel = page.split(b'class="home-panel your-team-panel"', 1)[1].split(b'</a>', 1)[0]
    assert b'Bristol City' in panel
    assert b'Opens 10 October 2026 at 06:00' in panel
