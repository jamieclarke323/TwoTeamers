from datetime import timedelta
from pathlib import Path

from app.data_loader import (
    PLAYABLE_HOURS,
    QUIZ_TIMEZONE,
    UNLOCK_HOUR,
    _played_in_eligible_season,
    _unique_season_players,
    load_all_clubs,
    load_club_players,
    load_quizzes,
    normalise_name,
    WORKBOOK_SHEET_ALIASES,
)
import openpyxl

ROOT = Path(__file__).resolve().parents[2]


def test_discovers_92_clubs_across_four_leagues():
    clubs = load_all_clubs(ROOT)
    assert len(clubs) == 4
    assert sum(len(names) for names in clubs.values()) == 92


def test_loads_all_four_leagues_and_all_fixtures():
    leagues, quizzes = load_quizzes(ROOT)
    assert len(leagues[0].clubs) == 20
    assert len(leagues[1].clubs) == 24
    assert len(leagues[2].clubs) == 24
    assert len(leagues[3].clubs) == 24
    assert all(league.enabled for league in leagues)
    assert len(quizzes) == 2036
    empty_counts = {
        league.league_id: sum(
            not quiz.players for quiz in quizzes if quiz.league_id == league.league_id
        )
        for league in leagues
    }
    assert empty_counts == {
        "premier-league": 6,
        "championship": 0,
        "league-one": 2,
        "league-two": 2,
    }


def test_league_one_and_two_club_sheet_aliases_load():
    league_one = load_club_players(
        ROOT / "Two Teamers - League One.xlsx",
        {"Peterborough United", "Blackpool"},
    )
    league_two = load_club_players(
        ROOT / "Two Teamers - League Two.xlsx",
        {"Chesterfield", "Tranmere Rovers", "Barnet"},
    )
    assert league_one["Peterborough United"]
    assert league_one["Blackpool"]
    assert league_two["Chesterfield"]
    assert league_two["Tranmere Rovers"]
    assert league_two["Barnet"]


def test_spaced_stats_tabs_load_ids_and_clues():
    league_one = load_club_players(
        ROOT / "Two Teamers - League One.xlsx", {"Blackpool"}
    )
    league_two = load_club_players(
        ROOT / "Two Teamers - League Two.xlsx", {"Barnet"}
    )
    assert league_one["Blackpool"]
    assert league_two["Barnet"]
    assert any(player.player_id and player.apps != "" for player in league_one["Blackpool"].values())
    assert any(player.player_id and player.apps != "" for player in league_two["Barnet"].values())


def test_all_divisions_include_matchweek_46():
    _, quizzes = load_quizzes(ROOT)
    for league_id in ("league-one", "league-two"):
        assert max(quiz.matchweek for quiz in quizzes if quiz.league_id == league_id) == 46


def test_uses_season_membership_with_stats_from_paired_tab():
    rosters = load_club_players(ROOT / "Two Teamers - PremierLeague.xlsx", {"Arsenal"})
    assert rosters["Arsenal"]
    assert all(player.years != "" for player in rosters["Arsenal"].values())
    assert all(player.apps != "" for player in rosters["Arsenal"].values())
    assert any(player.nationality for player in rosters["Arsenal"].values())
    assert all(player.nationality != "Unverified" for player in rosters["Arsenal"].values())


def test_championship_rosters_load_nationality_values():
    rosters = load_club_players(
        ROOT / "Two Teamers - Championship.xlsx", {"Birmingham City"}
    )
    assert rosters["Birmingham City"]
    assert any(player.nationality for player in rosters["Birmingham City"].values())


def test_duplicate_stats_names_are_distinguished_by_id():
    rosters = load_club_players(ROOT / "Two Teamers - PremierLeague.xlsx", {"Brentford"})
    players = [player for player in rosters["Brentford"].values() if player.name == "Paul Smith"]
    assert len(players) == 1
    assert players[0].player_id == "e50d714b"


def test_workbook_sheet_aliases_map_to_fixture_club_names():
    rosters = load_club_players(
        ROOT / "Two Teamers - PremierLeague.xlsx",
        {"Brighton & Hove Albion", "Coventry City"},
    )
    assert rosters["Brighton & Hove Albion"]
    assert rosters["Coventry City"]


def test_eligible_season_cutoff_handles_years_and_ranges():
    assert _played_in_eligible_season("1999") is True
    assert _played_in_eligible_season("1999-2000") is True
    assert _played_in_eligible_season("1998-2001") is True
    assert _played_in_eligible_season("1998-1999") is False
    assert _played_in_eligible_season("1986-1998") is False
    assert _played_in_eligible_season("1998") is False


def test_club_rosters_only_contain_players_with_eligible_stats_years():
    leagues, _ = load_quizzes(ROOT)
    for league_id, workbook_name in (
        ("premier-league", "Two Teamers - PremierLeague.xlsx"),
        ("championship", "Two Teamers - Championship.xlsx"),
        ("league-one", "Two Teamers - League One.xlsx"),
        ("league-two", "Two Teamers - League Two.xlsx"),
    ):
        league = next(item for item in leagues if item.league_id == league_id)
        rosters = load_club_players(ROOT / workbook_name, set(league.clubs))
        workbook = openpyxl.load_workbook(ROOT / workbook_name, read_only=True, data_only=True)
        for club, roster in rosters.items():
            sheet = workbook[WORKBOOK_SHEET_ALIASES.get(club, club)]
            memberships = _unique_season_players(sheet)
            for player in roster.values():
                key = normalise_name(player.name)
                assert any(_played_in_eligible_season(season) for season in memberships[key][1])
                if player.player_id:
                    assert _played_in_eligible_season(player.years)
        workbook.close()


def test_cardiff_charlton_rosters_include_karlan_grant():
    workbook_path = ROOT / "Two Teamers - Championship.xlsx"
    rosters = load_club_players(workbook_path, {"Cardiff City", "Charlton Athletic"})
    cardiff = next(player for player in rosters["Cardiff City"].values() if player.name == "Karlan Grant")
    charlton = next(player for player in rosters["Charlton Athletic"].values() if player.name == "Karlan Grant")
    assert cardiff.player_id == charlton.player_id == "87f7500e"


def test_loaded_fixture_players_are_only_present_at_both_clubs_since_cutoff():
    data_dir = ROOT
    leagues, quizzes = load_quizzes(data_dir)
    rosters = {}
    for league_id, workbook_name in (
        ("premier-league", "Two Teamers - PremierLeague.xlsx"),
        ("championship", "Two Teamers - Championship.xlsx"),
        ("league-one", "Two Teamers - League One.xlsx"),
        ("league-two", "Two Teamers - League Two.xlsx"),
    ):
        rosters.update(
            load_club_players(data_dir / workbook_name, set(next(l for l in leagues if l.league_id == league_id).clubs))
        )
    for quiz in quizzes:
        for player in quiz.players:
            assert player.home in rosters[quiz.home_team].values()
            assert player.away in rosters[quiz.away_team].values()
            assert player.home.identity == player.away.identity


def test_fixture_playable_window_matches_configured_hours_from_unlock_hour():
    _, quizzes = load_quizzes(ROOT)
    quiz = quizzes[0]
    assert quiz.unlock_at.hour == UNLOCK_HOUR
    assert quiz.lock_at == quiz.unlock_at + timedelta(hours=PLAYABLE_HOURS)
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
    assert quiz.unlock_at.isoformat() == f"2026-09-20T{UNLOCK_HOUR:02d}:00:00+01:00"
    assert quiz.lock_at == quiz.unlock_at + timedelta(hours=PLAYABLE_HOURS)
