from dataclasses import replace

import pytest
from openpyxl import Workbook

from app.data_loader import ClubPlayer, QuizPlayer, _stats_players, load_club_players
from app.db import get_progress
from test_offline import offline_app, offline_client


@pytest.mark.parametrize("position", ["CB", "CM, AM", "-", None])
def test_position_is_loaded_from_column_i_and_missing_values_are_omitted(tmp_path, position):
    workbook = Workbook()
    seasons = workbook.active
    seasons.title = "Home"
    seasons.append(["Rk", "Team", "Season", "Count", "Player List"])
    seasons.append(["", "", "", "", ""])
    seasons.append([1, "Home", "2020-2021", 1, "Test Player"])
    stats = workbook.create_sheet("HomeStats")
    stats.append(["Player", "Yrs", "MP", "Min", "Gls", "Ast", "Nationality", "PlayerId", "Position(s)"])
    stats.append(["Test Player", "2020-2021", 10, 900, 1, 0, "France", "test", position])
    parsed, _ = _stats_players(stats)
    expected = position if position not in ("-", None) else ""
    assert parsed["id:test"].position == expected
    path = tmp_path / "players.xlsx"
    workbook.save(path)
    assert load_club_players(path, {"Home"})["Home"]["id:test"].position == expected


def test_older_workbook_without_position_column_remains_supported():
    sheet = Workbook().active
    sheet.append(["Player", "Yrs", "MP", "Min", "Gls", "Ast", "Nationality", "PlayerId"])
    sheet.append(["Test Player", "2020", 10, 900, 1, 0, "France", "test"])
    players, _ = _stats_players(sheet)
    assert players["id:test"].position == ""


@pytest.mark.parametrize("home, away, expected", [
    ("CB", "CB", "CB"), ("CB", "", "CB"), ("", "ST", "ST"),
    ("CM", "AM", "CM / AM"), ("", "", ""),
])
def test_position_uses_available_club_records(home, away, expected):
    player = QuizPlayer("Test Player", ClubPlayer("Test Player", "2020", 10, 1, position=home),
                        ClubPlayer("Test Player", "2021", 10, 1, position=away))
    assert player.position == expected
    assert player.has_clue("position") == bool(expected)


@pytest.mark.parametrize("target", [0, "all"])
def test_position_clues_online_offline_replay_persistence_and_scoring(
    offline_app, offline_client, target
):
    quiz = offline_app.config["QUIZZES"][0]
    quiz.players[0].home = replace(quiz.players[0].home, position="CB")
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert '"positionPlayerIndices": [0]' in page
    assert "Position: CB" not in page
    downloaded = offline_client.post("/quiz/offline-test/offline-package").json
    pack = downloaded["package"]
    assert pack["players"][0]["clues"]["position"] == "CB"
    assert "position" not in pack["players"][1]["clues"]
    body = {"types": ["position"], "index": target}
    sync = offline_client.post("/quiz/offline-test/offline-sync", json={
        "token": pack["token"],
        "actions": [{"seq": 1, "at": pack["issuedAt"] + 1, "action": "clue", "body": body}],
    })
    assert sync.status_code == 200
    result = offline_client.post("/quiz/offline-test/clue", json=body)
    assert result.status_code == 200
    assert result.json["clues"][0] == {"index": 0, "position": "CB"}
    if target == "all":
        assert result.json["clues"][1] == {"index": 1}
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert "<strong>Position:</strong> CB" in page
    assert offline_client.post("/quiz/offline-test/clue", json={
        "types": ["position"], "index": 1,
    }).status_code == 400
    guess = offline_client.post("/quiz/offline-test/guess", json={"guess": "Gudmundsson"})
    assert guess.json["player"]["position"] == "CB"
    with offline_client.session_transaction() as session:
        identity = session["visitor_id"]
    with offline_app.app_context():
        state = get_progress(identity, quiz.quiz_id)
        assert state["answer_data"]["clues"]["0"] == ["position"]
        assert state["answer_data"]["solve_order"][0]["clue_count"] == 1
        assert state["score_frozen"] is True
    offline_client.post("/quiz/offline-test/reset", json={})
    assert "<strong>Position:</strong> CB" not in offline_client.get("/quiz/offline-test").get_data(as_text=True)


def test_position_obeys_existing_ad_gate(offline_app, offline_client):
    offline_app.config["REWARDED_ADS_ENABLED"] = True
    player = offline_app.config["QUIZZES"][0].players[0]
    player.home = replace(player.home, position="CB")
    response = offline_client.post("/quiz/offline-test/clue", json={"types": ["position"], "index": 0})
    assert response.status_code == 403
    assert response.json["status"] == "ad_required"
    assert offline_client.post("/quiz/offline-test/clue-unlock").status_code == 200
    assert offline_client.post("/quiz/offline-test/clue", json={
        "types": ["position"], "index": 0,
    }).json["clues"][0]["position"] == "CB"


@pytest.mark.parametrize("action", ["guess", "giveup", "giveup-answer"])
def test_resolved_cards_include_available_position(offline_app, offline_client, action):
    player = offline_app.config["QUIZZES"][0].players[0]
    player.home = replace(player.home, position="CB")
    result = offline_client.post(f"/quiz/offline-test/{action}", json={
        "guess": "Gudmundsson", "confirm": True, "index": 0,
    })
    assert result.status_code == 200
    answer = result.json.get("player") or result.json["players"][0]
    assert answer["position"] == "CB"
    assert "Position: CB" in offline_client.get("/quiz/offline-test").get_data(as_text=True)
    snapshot = offline_client.post("/quiz/offline-test/offline-package").json
    assert "Position: CB" in snapshot["html"]


def test_games_without_positions_hide_option_and_reject_unavailable_clue(offline_client):
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert '<label id="position-clue-option" hidden>' in page
    assert '"positionPlayerIndices": []' in page
    response = offline_client.post("/quiz/offline-test/clue", json={
        "types": ["position"], "index": "all",
    })
    assert response.status_code == 400
    assert response.json["message"] == "That clue is not available."
