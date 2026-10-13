from dataclasses import replace
from datetime import datetime, timedelta
from urllib.parse import quote

from app.badges import BADGE_FILES
from app.data_loader import QUIZ_TIMEZONE, UNLOCK_HOUR, _featured_club_name, normalise_name
from app.routes import todays_featured_quiz


def _featured(app, home, away):
    return next(
        quiz for quiz in app.config["FEATURED_QUIZZES"]
        if (quiz.home_team, quiz.away_team) == (home, away)
    )


def test_featured_list_loads_real_and_wildcard_fixtures(app):
    featured = app.config["FEATURED_QUIZZES"]
    assert featured
    assert len({quiz.fixture_date.date() for quiz in featured}) == len(featured)

    wildcard = _featured(app, "Charlton Athletic", "Manchester United")
    assert wildcard.wildcard
    assert wildcard.fixture_date.date().isoformat() == "2026-10-08"
    # Cross-league wildcard still finds players who played for both clubs.
    assert wildcard.players

    real = _featured(app, "West Ham United", "Queens Park Rangers")
    assert not real.wildcard
    assert (real.fixture_date.hour, real.fixture_date.minute) == (20, 0)
    assert real.venue == "London Stadium"


def test_featured_short_names_map_to_club_names():
    assert _featured_club_name("Ason Villa") == "Aston Villa"
    assert _featured_club_name("Sheffield Utd") == "Sheffield United"
    assert _featured_club_name("Brighton and Hove Albion") == "Brighton & Hove Albion"


def test_featured_day_switches_just_after_midnight(app):
    quiz = app.config["FEATURED_QUIZZES"][1]
    day = quiz.fixture_date.date()
    with app.app_context():
        at_unlock = datetime(day.year, day.month, day.day, 0, 1, tzinfo=QUIZ_TIMEZONE)
        before_unlock = datetime(day.year, day.month, day.day, 0, 0, 30, tzinfo=QUIZ_TIMEZONE)
        assert todays_featured_quiz(at_unlock) is quiz
        assert todays_featured_quiz(before_unlock) is not quiz
    assert quiz.unlock_at == at_unlock
    assert quiz.availability(at_unlock) == "playable"
    assert quiz.availability(before_unlock) == "upcoming"


def test_regular_games_still_open_at_unlock_hour(app):
    assert app.config["QUIZZES"][0].unlock_at.hour == UNLOCK_HOUR


def _make_today(app):
    base = _featured(app, "Charlton Athletic", "Manchester United")
    now = datetime.now(QUIZ_TIMEZONE) - timedelta(minutes=1)
    today = replace(base, fixture_date=now.replace(hour=0, minute=0, second=0, microsecond=0))
    app.config["FEATURED_QUIZZES"] = [today]
    app.config["QUIZZES_BY_ID"][today.quiz_id] = today
    return today


def test_featured_banner_shows_on_non_game_pages_with_kits(client, app):
    _make_today(app)
    for path in ("/teams", "/leagues", "/login"):
        page = client.get(path).data
        assert b'class="featured-fixture"' in page
        assert b'href="/featured"' in page
        assert f"img/kits/{quote(BADGE_FILES['Charlton Athletic'])}".encode() in page
        assert f"img/kits/{quote(BADGE_FILES['Manchester United'])}".encode() in page
        assert b"Today&#39;s featured fixture" in page or b"Today's featured fixture" in page
        assert b"Wildcard" not in page


def test_home_page_links_to_featured_game_without_banner(client, app):
    today = _make_today(app)
    game = client.get("/")
    assert game.status_code == 200
    assert b"Charlton Athletic" in game.data
    assert b'class="featured-fixture"' not in game.data
    assert b'class="home-panel featured-home-panel" href="/featured"' in game.data
    assert client.get(f"/quiz/{today.quiz_id}").headers["Location"].endswith("/featured")
    assert client.get("/featured").status_code == 200
    assert client.post(f"/quiz/{today.quiz_id}/guess", json={"guess": today.players[0].name}).get_json()["status"] == "correct"


def test_navbar_has_pick_team_and_pick_league_buttons(client):
    page = client.get("/").data
    assert b'class="header-nav"' in page
    assert b'href="/teams"' in page
    assert b"Pick a team" in page
    assert b'href="/leagues"' in page
    assert b"Pick a league" in page


def test_quiz_page_has_how_to_play_and_clue_info_dialogs(client, app):
    quiz = app.config["QUIZZES"][0]
    page = client.get(f"/quiz/{quiz.quiz_id}").data
    assert b'id="how-to-play-btn"' in page
    assert b"Name the footballers who have played for both of the (men&#39;s) teams listed" in page or b"Name the footballers who have played for both of the (men's) teams listed" in page
    assert b"If you&#39;re unsure of the spelling, click &#39;Guess&#39;" in page or b"If you're unsure of the spelling, click 'Guess'" in page
    assert b"Please note that Apps/Goals stats may include U21 figures" in page
    assert b'id="clue-info-btn"' in page
    assert b'id="stats-info-dialog"' in page


def test_regular_quiz_page_hides_banner(client, app):
    _make_today(app)
    quiz = app.config["QUIZZES"][0]
    assert b'class="featured-fixture"' not in client.get(f"/quiz/{quiz.quiz_id}").data


def test_featured_url_redirects_home_when_no_fixture(client, app):
    app.config["FEATURED_QUIZZES"] = []
    response = client.get("/featured")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_players_are_ordered_by_surname(app):
    for quiz in [*app.config["QUIZZES"][:50], *app.config["FEATURED_QUIZZES"]]:
        surnames = [normalise_name(player.name.split()[-1]) for player in quiz.players]
        assert surnames == sorted(surnames)


def test_no_banner_when_no_featured_fixture_today(client, app):
    app.config["FEATURED_QUIZZES"] = []
    assert b'class="featured-fixture"' not in client.get("/").data


def test_champions_league_wildcard_available_in_featured_quizzes(app):
    atletico_quiz = next(
        (quiz for quiz in app.config["FEATURED_QUIZZES"]
         if quiz.home_team == "Atletico Madrid" and quiz.away_team == "Manchester United"),
        None,
    )
    assert atletico_quiz is not None
    assert len(atletico_quiz.players) == 6


def test_champions_league_teams_not_on_home_or_teams_page(client):
    home = client.get("/").data
    assert b'data-club="Real Madrid"' not in home
    assert b"Champions League" not in home

    teams = client.get("/teams").data
    assert b'data-club="Real Madrid"' not in teams
    assert b'data-club="Atletico Madrid"' not in teams


def test_admin_matchup_screen_generates_all_answers(client):
    response = client.get("/admin?team1=Charlton+Athletic&team2=Portsmouth")
    assert response.status_code == 200
    assert b"41" in response.data
    assert b"player" in response.data
    assert b"Paul Benson" in response.data
    assert b"Charlton Athletic: 2010-2011" in response.data
    assert b"Portsmouth: 2012" in response.data


def test_admin_screen_not_linked_in_navbar_or_home(client):
    home = client.get("/").data
    assert b'href="/admin"' not in home
    assert b'href="/admin/matchup"' not in home
    teams = client.get("/teams").data
    assert b'href="/admin"' not in teams
