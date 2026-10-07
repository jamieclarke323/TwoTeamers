from datetime import datetime, timedelta
from pathlib import Path

from app.badges import BADGE_FILES
from app.data_loader import QUIZ_TIMEZONE
from app.db import get_progress

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_visitors_are_sent_to_login(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Pick a team" in response.data
    assert b"Log in" in response.data


def test_home_offers_team_and_league_paths(signed_in_client):
    response = signed_in_client.get("/")
    assert b"Pick a team" in response.data
    assert b"Pick a league" in response.data


def test_pwa_manifest_and_badge_icon_are_linked(client):
    page = client.get("/")
    assert b'rel="manifest"' in page.data
    assert b"two-teamers-app-icon.svg" in page.data

    manifest = client.get("/static/manifest.webmanifest")
    assert manifest.status_code == 200
    assert b'"display": "standalone"' in manifest.data
    assert b'"purpose": "any maskable"' in manifest.data
    icon = client.get("/static/img/two-teamers-app-icon.svg")
    assert icon.status_code == 200
    assert b"<svg" in icon.data


def test_team_picker_contains_all_92_clubs(signed_in_client):
    response = signed_in_client.get("/teams")
    assert response.status_code == 200
    assert response.data.count(b'data-club="') == 92
    # Featured banner kits are decorative (alt=""), so only club tiles match.
    assert response.data.count(b' home kit"') == 92
    assert b"/static/img/kits/Arsenal.png" in response.data
    assert b'data-club="Sunderland"' in response.data
    assert b"/static/img/kits/Sunderland.png" in response.data


def test_every_configured_badge_asset_exists():
    badge_directory = PROJECT_ROOT / "app" / "static" / "img" / "kits"
    assert len(BADGE_FILES) == 92
    assert all((badge_directory / filename).is_file() for filename in BADGE_FILES.values())


def test_team_search_hidden_attribute_hides_explicitly_flex_tiles():
    stylesheet = (PROJECT_ROOT / "app" / "static" / "css" / "style.css").read_text()
    assert "[hidden]{display:none!important}" in stylesheet


def test_premier_league_page_lists_one_matchweek(signed_in_client):
    response = signed_in_client.get("/league/premier-league")
    assert response.status_code == 200
    assert response.data.count(b'class="fixture-row') == 10


def test_team_fixtures_auto_scroll_to_first_playable_fixture(client, app):
    team = "Arsenal"
    first_playable = next(
        quiz
        for quiz in app.config["QUIZZES"]
        if team in (quiz.home_team, quiz.away_team)
    )
    response = client.get("/team/arsenal")
    assert response.status_code == 200
    assert (
        f'id="first-playable-fixture" href="/quiz/{first_playable.quiz_id}"'.encode()
        in response.data
    )
    assert b"js/fixture-scroll.js" in response.data


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


def test_clues_are_not_ad_gated_by_default(client, app):
    quiz = app.config["QUIZZES"][0]
    page = client.get(f"/quiz/{quiz.quiz_id}")
    assert b"Watch an ad to unlock clues!" not in page.data
    assert b"js/ads.js" not in page.data


def test_rewarded_ads_lock_clues_until_ad_watched(client, app):
    app.config["REWARDED_ADS_ENABLED"] = True
    quiz = app.config["QUIZZES"][0]
    page = client.get(f"/quiz/{quiz.quiz_id}")
    assert b"Watch an ad to unlock clues!" in page.data
    assert b'value="apps" disabled' in page.data
    assert b"js/ads.js" in page.data

    clue_url = f"/quiz/{quiz.quiz_id}/clue"
    locked = client.post(clue_url, json={"types": ["apps"], "index": 0})
    assert locked.status_code == 403
    assert locked.get_json()["status"] == "ad_required"

    assert client.post(f"/quiz/{quiz.quiz_id}/clue-unlock", json={}).get_json()["status"] == "unlocked"
    assert b'value="apps" disabled' not in client.get(f"/quiz/{quiz.quiz_id}").data
    assert client.post(clue_url, json={"types": ["apps"], "index": 0}).status_code == 200
    # One ad pays for one reveal.
    assert client.post(clue_url, json={"types": ["goals"], "index": 0}).status_code == 403


def test_adsense_script_loads_only_with_client_id(client, app):
    app.config["REWARDED_ADS_ENABLED"] = True
    quiz = app.config["QUIZZES"][0]
    assert b"adsbygoogle.js" not in client.get(f"/quiz/{quiz.quiz_id}").data
    app.config["ADSENSE_CLIENT_ID"] = "ca-pub-1234567890"
    page = client.get(f"/quiz/{quiz.quiz_id}").data
    assert b"adsbygoogle.js?client=ca-pub-1234567890" in page
    assert b'data-adbreak-test="on"' in page


def test_quiz_page_displays_player_season_cutoff(signed_in_client, app):
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    response = signed_in_client.get(f"/quiz/{quiz.quiz_id}")
    assert b"Only players from 2000 onwards, excluding the most recent season, are valid for this game" in response.data


def test_quiz_script_labels_numeric_clues():
    script_path = PROJECT_ROOT / "app" / "static" / "js" / "quiz.js"
    script = script_path.read_text()
    assert 'apps: "Apps"' in script
    assert 'goals: "Goals"' in script
    assert 'initials: "Initials"' in script


def test_share_result_uses_original_card_order_and_clue_count(signed_in_client, app):
    quiz = next(quiz for quiz in app.config["QUIZZES"] if len(quiz.players) >= 4)
    # Solve later cards first, leaving card zero unanswered to verify display order.
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/clue",
        json={"types": ["apps", "goals"], "index": 1},
    )
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[1].name}
    )
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/clue",
        json={"types": ["years"], "index": 2},
    )
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[2].name}
    )

    result = signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/giveup", json={"confirm": True}
    ).get_json()
    lines = result["share_text"].splitlines()
    assert lines[0] == f"TWO TEAMERS 2/{quiz.total_players}"
    assert lines[1] == f"{quiz.home_team} vs {quiz.away_team}"
    assert lines[2].split() == ["❌", "🟠", "🟡"] + ["❌"] * (quiz.total_players - 3)
    assert lines[3] == "www.placeholderlink.com"


def test_completing_game_returns_share_text_from_normal_guess_flow(signed_in_client, app):
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    quiz.players = quiz.players[:1]
    result = signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    ).get_json()
    assert result["completed"] is True
    assert result["share_text"].splitlines() == [
        "TWO TEAMERS 1/1",
        f"{quiz.home_team} vs {quiz.away_team}",
        "🟢",
        "www.placeholderlink.com",
    ]
    page = signed_in_client.get(f"/quiz/{quiz.quiz_id}")
    assert b'"completed": true' in page.data
    assert b'"shareText": "TWO TEAMERS 1/1' in page.data


def test_finished_quiz_shows_share_prompt_and_copy_toast_markup(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    response = signed_in_client.get(f"/quiz/{quiz.quiz_id}")
    assert response.status_code == 200
    assert b"share-dialog" in response.data
    assert b"Share your results?" in response.data
    assert b"Copied to clipboard!" in response.data
    script = (PROJECT_ROOT / "app" / "static" / "js" / "quiz.js").read_text()
    assert "navigator.clipboard.writeText(shareText)" in script


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


def test_league_one_supports_matchweek_46_and_keeps_its_league_link(signed_in_client):
    response = signed_in_client.get("/league/league-one?week=46")
    assert response.status_code == 200
    assert b"Matchweek 46 of 46" in response.data
    assert b"/league/league-one?week=45" in response.data


def test_league_two_supports_matchweek_46(signed_in_client):
    response = signed_in_client.get("/league/league-two?week=46")
    assert response.status_code == 200
    assert b"Matchweek 46 of 46" in response.data


def test_guest_can_browse_teams_leagues_fixtures_and_game(client, app):
    assert client.get("/teams").status_code == 200
    assert client.get("/leagues").status_code == 200
    assert client.get("/league/league-one?week=1").status_code == 200
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    assert client.get(f"/quiz/{quiz.quiz_id}").status_code == 200


def test_guest_game_progress_persists_in_same_browser(client, app):
    quiz = next(quiz for quiz in app.config["QUIZZES"] if quiz.players)
    guess = client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    )
    assert guess.get_json()["status"] == "correct"
    page = client.get(f"/quiz/{quiz.quiz_id}")
    assert quiz.players[0].name.encode() in page.data


def test_profile_and_leaderboard_still_require_login(client):
    assert client.get("/profile").location.endswith("/login?next=/profile")
    assert client.get("/leaderboard").location.endswith("/login?next=/leaderboard")


def test_zero_overlap_fixture_is_explained_not_rendered_as_empty_quiz(signed_in_client, app):
    quiz = next(
        quiz
        for quiz in app.config["QUIZZES"]
        if quiz.league_id == "league-one" and quiz.total_players == 0
    )
    response = signed_in_client.get(f"/quiz/{quiz.quiz_id}")
    assert response.status_code == 200
    assert b"NO PLAYERS" in response.data
    assert b"does not list any players" in response.data
