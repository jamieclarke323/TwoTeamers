from pathlib import Path

from openpyxl import Workbook

from app.data_loader import _shared_players, _stats_players, load_club_players
from app.matching import MatchResult, match_guess


def test_duplicate_name_keeps_only_eligible_record():
    sheet = Workbook().active
    sheet.append(["Andy Gray", "2007-2009", 45, 2791, 9])
    sheet.append(["Andy Gray", 1993, 0, None, 0])
    records, ambiguous = _stats_players(sheet)
    assert "andygray" not in ambiguous
    assert records["andygray"].years == "2007-2009"
    assert records["andygray"].apps == 45
    assert records["andygray"].goals == 9


def test_duplicate_name_with_multiple_eligible_records_stays_ambiguous():
    sheet = Workbook().active
    sheet.append(["Same Name", "2007-2009", 45, None, 9])
    sheet.append(["Same Name", "2010-2012", 20, None, 2])
    records, ambiguous = _stats_players(sheet)
    assert "samename" not in records
    assert "samename" in ambiguous


def test_andy_gray_is_accepted_for_burnley_charlton():
    root = Path(__file__).resolve().parents[2]
    rosters = load_club_players(
        root / "Two Teamers - Championship.xlsx", {"Burnley", "Charlton Athletic"}
    )
    players = _shared_players(rosters, "Burnley", "Charlton Athletic")
    outcome = match_guess("Andy Gray", players, set())
    assert outcome.result == MatchResult.EXACT
    player = players[outcome.player_index]
    assert (player.home.apps, player.home.goals) == (70, 29)
    assert (player.away.apps, player.away.goals) == (45, 9)