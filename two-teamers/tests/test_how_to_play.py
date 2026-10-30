from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.data_loader import QUIZ_TIMEZONE
from app.db import get_db
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("signed_in", [False, True])
def test_home_and_quiz_share_rules_and_expose_login_state(offline_app, offline_client, signed_in):
    if signed_in:
        with offline_app.app_context():
            db = get_db()
            db.execute("INSERT INTO users (id,email,password_hash) VALUES (1,'fan@example.com','hash')")
            db.commit()
        with offline_client.session_transaction() as browser_session:
            browser_session["user_id"] = 1

    pages = [offline_client.get(path).get_data(as_text=True) for path in ("/", "/quiz/offline-test")]
    for page in pages:
        assert page.count('id="how-to-play-dialog"') == 1
        assert 'id="how-to-play-btn"' in page
        assert 'aria-labelledby="how-to-play-title"' in page
        assert 'js/how-to-play.js' in page
        assert f'data-authenticated="{str(signed_in).lower()}"' in page
    home_rules = pages[0].split('<dialog id="how-to-play-dialog"', 1)[1].split("</dialog>", 1)[0]
    quiz_rules = pages[1].split('<dialog id="how-to-play-dialog"', 1)[1].split("</dialog>", 1)[0]
    assert home_rules == quiz_rules


def test_other_pages_track_visits_without_showing_rules(offline_client):
    page = offline_client.get("/teams").get_data(as_text=True)
    assert 'js/how-to-play.js' in page
    assert 'id="how-to-play-dialog"' not in page


def test_locked_quiz_includes_rules(offline_app, offline_client):
    quiz = replace(
        offline_app.config["QUIZZES"][0],
        fixture_date=datetime.now(QUIZ_TIMEZONE) + timedelta(days=5),
    )
    offline_app.config["BYPASS_AVAILABILITY"] = False
    offline_app.config["QUIZZES_BY_ID"][quiz.quiz_id] = quiz
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert 'id="how-to-play-dialog"' in page


def test_offline_download_includes_shared_rules_and_script(offline_client):
    download = offline_client.post("/quiz/offline-test/offline-package").get_json()
    assert download["html"].count('id="how-to-play-dialog"') == 1
    assert 'id="how-to-play-btn"' in download["html"]
    assert '/static/js/how-to-play.js' in download["assets"]
    for asset in download["assets"]:
        assert offline_client.get(asset).status_code == 200
