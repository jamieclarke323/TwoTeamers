from datetime import datetime, timedelta
from pathlib import Path

from app.badges import BADGE_FILES
from app.data_loader import QUIZ_TIMEZONE
from app.db import get_progress

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_visitors_are_sent_to_login(client):
    assert client.get("/").location.endswith("/login?next=/")


def test_home_offers_team_and_league_paths(signed_in_client):
    response = signed_in_client.get("/")
    assert b"Pick a team" in response.data
    assert b"Pick a league" in response.data


def test_team_picker_contains_all_92_clubs(signed_in_client):
    response = signed_in_client.get("/teams")
    assert response.status_code == 200
    assert response.data.count(b'data-club="') == 92
    assert response.data.count(b"/static/img/badges/") == 43
    assert b"/static/img/badges/Arsenal.png" in response.data
    assert b'<span class="club-mark">S</span>' in response.data


def test_every_configured_badge_asset_exists():
    badge_directory = PROJECT_ROOT / "app" / "static" / "img" / "badges"
    assert len(BADGE_FILES) == 43
    assert all((badge_directory / filename).is_file() for filename in BADGE_FILES.values())


def test_premier_league_page_lists_one_matchweek(signed_in_client):
    response = signed_in_client.get("/league/premier-league")
    assert response.status_code == 200
    assert response.data.count(b'class="fixture-row') == 10


def test_upcoming_fixture_status_shows_fixture_date(signed_in_client, app):
    app.config["BYPASS_AVAILABILITY"] = False
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.availability() == "upcoming")
    response = signed_in_client.get(f"/league/{quiz.league_id}?week={quiz.matchweek}")
    assert f"opens {quiz.fixture_date.strftime('%d/%m')}".encode() in response.data
    assert b"opens 4am" not in response.data


def test_correct_guess_persists_to_account(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    response = signed_in_client.post(f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].surname})
    assert response.get_json()["status"] == "correct"
    with app.app_context():
        assert get_progress(1, quiz.quiz_id)["solved"] == [0]


def test_clue_endpoint_returns_derived_initials(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    response = signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/clue",
        json={"types": ["initials"], "index": 0},
    )
    assert response.status_code == 200
    assert response.get_json()["clues"] == [
        {"index": 0, "initials": quiz.players[0].initials}
    ]


def test_quiz_page_offers_initials_clue(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    response = signed_in_client.get(f"/quiz/{quiz.quiz_id}")
    assert b'value="initials"' in response.data


def test_quiz_script_labels_numeric_clues():
    script_path = PROJECT_ROOT / "app" / "static" / "js" / "quiz.js"
    script = script_path.read_text()
    assert 'apps: "Apps"' in script
    assert 'goals: "Goals"' in script
    assert 'initials: "Initials"' in script


def test_expired_quiz_is_locked(signed_in_client, app):
    app.config["BYPASS_AVAILABILITY"] = False
    quiz = app.config["QUIZZES"][0]
    quiz.fixture_date = datetime.now(QUIZ_TIMEZONE) - timedelta(days=31)
    response = signed_in_client.post(f"/quiz/{quiz.quiz_id}/guess", json={"guess": "anything"})
    assert response.status_code == 403
    assert response.get_json()["status"] == "expired"


def test_leaderboard_lists_all_teams_and_period_controls(signed_in_client):
    response = signed_in_client.get("/leaderboard")
    assert response.status_code == 200
    assert response.data.count(b'data-team="') == 92
    assert b"Season" in response.data
    assert b"Matchweek" in response.data
    assert b"Choose a team" in response.data
    labels = response.data.split(b'class="leaderboard-row leaderboard-labels"', 1)[1].split(b"</div>", 1)[0]
    assert b">Fans<" not in labels


def test_matchweek_leaderboard_renders_selected_week(signed_in_client):
    response = signed_in_client.get("/leaderboard?mode=matchweek&week=3")
    assert response.status_code == 200
    assert b'<option value="3" selected>3</option>' in response.data
