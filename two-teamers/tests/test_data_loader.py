from datetime import timedelta
from pathlib import Path

from app.data_loader import QUIZ_TIMEZONE, load_all_clubs, load_club_players, load_quizzes

ROOT = Path(__file__).resolve().parents[2]


def test_discovers_92_clubs_across_four_leagues():
    clubs = load_all_clubs(ROOT)
    assert len(clubs) == 4
    assert sum(len(names) for names in clubs.values()) == 92


def test_loads_all_premier_league_and_championship_fixtures():
    leagues, quizzes = load_quizzes(ROOT)
    assert len(leagues[0].clubs) == 20
    assert len(leagues[1].clubs) == 24
    assert len(quizzes) == 932
    assert all(quiz.players for quiz in quizzes)


def test_uses_season_membership_with_stats_from_paired_tab():
    rosters = load_club_players(ROOT / "Two Teamers - PremierLeague.xlsx", {"Arsenal"})
    assert rosters["Arsenal"]
    assert all(player.years != "" for player in rosters["Arsenal"].values())
    assert all(player.apps != "" for player in rosters["Arsenal"].values())


def test_ambiguous_duplicate_stats_names_are_not_merged():
    rosters = load_club_players(ROOT / "Two Teamers - PremierLeague.xlsx", {"Brentford"})
    assert "paulsmith" not in rosters["Brentford"]


def test_workbook_sheet_aliases_map_to_fixture_club_names():
    rosters = load_club_players(
        ROOT / "Two Teamers - PremierLeague.xlsx",
        {"Brighton & Hove Albion", "Coventry City"},
    )
    assert rosters["Brighton & Hove Albion"]
    assert rosters["Coventry City"]


def test_fixture_has_seventy_two_hour_playable_window_from_4am():
    _, quizzes = load_quizzes(ROOT)
    quiz = quizzes[0]
    assert quiz.unlock_at.hour == 4
    assert quiz.lock_at == quiz.unlock_at + timedelta(hours=72)
    assert quiz.availability(quiz.unlock_at) == "playable"
    assert quiz.availability(quiz.lock_at) == "expired"
    assert quiz.availability(quiz.unlock_at - timedelta(minutes=1)) == "upcoming"


def test_fulham_manchester_united_window_matches_fixture_date():
    _, quizzes = load_quizzes(ROOT)
    quiz = next(
        quiz
        for quiz in quizzes
        if quiz.home_team == "Fulham"
        and quiz.away_team == "Manchester United"
        and quiz.fixture_date.day == 20
        and quiz.fixture_date.month == 9
    )
    assert quiz.unlock_at.isoformat() == "2026-09-20T04:00:00+01:00"
    assert quiz.lock_at.isoformat() == "2026-09-23T04:00:00+01:00"
