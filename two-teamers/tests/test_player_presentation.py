import json
import struct
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pytest

from app.badges import BADGE_FILES
from app.data_loader import ClubPlayer, QuizPlayer
from test_offline import offline_app, offline_client


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class PlayerCards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "button" and "data-index" in dict(attrs):
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "button":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.text.append(data)


@pytest.mark.parametrize(("home", "away", "expected"), [
    ("France", "France", "🇫🇷 France"),
    ("", "", ""),
    ("France", "", "🇫🇷 France"),
    ("", "France", "🇫🇷 France"),
    ("Ireland", "Republic of Ireland", "🇮🇪 Ireland"),
    ("France", "Spain", "🇫🇷 France / 🇪🇸 Spain"),
    ("Unmapped country", "", "Unmapped country"),
])
def test_answer_nationality_uses_available_records_without_empty_parts(
    offline_app, offline_client, home, away, expected
):
    quiz = offline_app.config["QUIZZES"][0]
    quiz.players[0] = QuizPlayer(
        "Test Player", ClubPlayer("Test Player", "2020", 10, 1, home, "test"),
        ClubPlayer("Test Player", "2021", 20, 2, away, "test"),
    )
    guess = offline_client.post("/quiz/offline-test/guess", json={"guess": "Test Player"})
    assert guess.json["player"]["nationality"] == expected
    assert quiz.players[0].has_nationality is bool(home or away)
    snapshot = offline_client.post("/quiz/offline-test/offline-package").json
    assert snapshot["package"]["players"][0]["nationality"] == expected
    for page in (offline_client.get("/quiz/offline-test").get_data(as_text=True), snapshot["html"]):
        parser = PlayerCards()
        parser.feed(page)
        text = " ".join(parser.text)
        assert "Test Player" in text
        assert "Home: 2020" in text
        assert "Away: 2021" in text
        assert " apps" not in text
        assert " goals" not in text
        if expected:
            assert expected in text
        else:
            assert "France" not in text
            assert "Nationality" not in text


@pytest.mark.parametrize("action", ["giveup", "giveup-answer"])
def test_revealing_answers_includes_nationality_without_changing_scores(offline_app, offline_client, action):
    response = offline_client.post(
        f"/quiz/offline-test/{action}", json={"confirm": True, "index": 0}
    )
    players = response.json.get("players") or [response.json["player"]]
    assert all(player["nationality"] == "🇫🇷 France" for player in players)
    parser = PlayerCards()
    parser.feed(offline_client.get("/quiz/offline-test").get_data(as_text=True))
    text = " ".join(parser.text)
    assert "🇫🇷 France" in text
    assert " apps" not in text and " goals" not in text


@pytest.mark.parametrize(("home", "away"), [("France", ""), ("", "France")])
@pytest.mark.parametrize("target", [0, "all"])
def test_single_record_nationality_clues_work_online_and_in_offline_replay(
    offline_app, offline_client, home, away, target
):
    quiz = offline_app.config["QUIZZES"][0]
    quiz.players = [
        QuizPlayer("Test Player", ClubPlayer("Test Player", "2020", 10, 1, home),
                   ClubPlayer("Test Player", "2021", 20, 2, away)),
        QuizPlayer("Other Player", ClubPlayer("Other Player", "2020", 10, 1),
                   ClubPlayer("Other Player", "2021", 20, 2)),
    ]
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert '<label id="nationality-clue-option" hidden>' not in page
    assert '"nationalityPlayerIndices": [0]' in page
    downloaded = offline_client.post("/quiz/offline-test/offline-package").json
    pack = downloaded["package"]
    assert pack["players"][0]["clues"]["nationality"] == "🇫🇷 France"
    assert "nationality" not in pack["players"][1]["clues"]
    assert '"nationalityPlayerIndices": [0]' in downloaded["html"]

    body = {"types": ["nationality"], "index": target}
    synced = offline_client.post("/quiz/offline-test/offline-sync", json={
        "token": pack["token"],
        "actions": [{"seq": 1, "at": pack["issuedAt"] + 1, "action": "clue", "body": body}],
    })
    assert synced.status_code == 200
    assert "🇫🇷 France" in offline_client.get("/quiz/offline-test").get_data(as_text=True)
    response = offline_client.post("/quiz/offline-test/clue", json=body)
    assert response.status_code == 200
    clues = response.json["clues"]
    assert clues[0] == {"index": 0, "nationality": "🇫🇷 France"}
    if target == "all":
        assert clues[1] == {"index": 1}
    unavailable = offline_client.post(
        "/quiz/offline-test/clue", json={"types": ["nationality"], "index": 1}
    )
    assert unavailable.status_code == 400


def test_supplied_icons_are_used_for_all_app_surfaces(offline_client):
    manifest = offline_client.get("/static/manifest.webmanifest").json
    assert manifest["icons"] == [
        {"src": "/static/img/two-teamers-app-icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        {"src": "/static/img/two-teamers-app-icon.png", "sizes": "1080x1080", "type": "image/png", "purpose": "any"},
    ]
    for icon in manifest["icons"]:
        response = offline_client.get(icon["src"])
        assert response.status_code == 200
        assert response.mimetype == icon["type"]
        if icon["type"] == "image/png":
            assert response.data.startswith(b"\x89PNG\r\n\x1a\n")
            assert struct.unpack(">II", response.data[16:24]) == (1080, 1080)
        else:
            assert ElementTree.fromstring(response.data).tag == "{http://www.w3.org/2000/svg}svg"
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert 'img/two-teamers-app-icon.svg' in page
    assert 'rel="apple-touch-icon" href="/static/img/two-teamers-app-icon.png"' in page
    worker = offline_client.get("/service-worker.js").get_data(as_text=True)
    assert 'icon: "/static/img/two-teamers-app-icon.png"' in worker
    assert 'badge: "/static/img/two-teamers-app-icon.png"' in worker
    downloaded = offline_client.post("/quiz/offline-test/offline-package").json
    assert "/static/img/two-teamers-app-icon.svg" in downloaded["assets"]
    assert "/static/img/two-teamers-app-icon.png" in downloaded["assets"]
    assert all(offline_client.get(asset).status_code == 200 for asset in downloaded["assets"])
    assert "-192.png" not in worker and "-512.png" not in json.dumps(manifest)


@pytest.mark.parametrize("club", ["Celtic", "AC Milan", "Juventus", "Rangers"])
def test_supplied_kits_are_available(offline_client, club):
    response = offline_client.get(f"/static/img/kits/{BADGE_FILES[club]}")
    assert response.status_code == 200
    assert response.data.startswith(b"\x89PNG")


def test_extended_featured_rows_and_kit_coverage(app):
    import openpyxl

    from app.data_loader import FEATURED_SHEET, _featured_club_name

    workbook = openpyxl.load_workbook(app.config["FEATURED_XLSX_PATH"], read_only=True, data_only=True)
    try:
        populated = []
        for row in workbook[FEATURED_SHEET].iter_rows(min_row=2, values_only=True):
            row = tuple(row) + (None,) * max(0, 7 - len(row))
            if row[3] and row[4]:
                populated.append((row[0].date(), _featured_club_name(row[3]), _featured_club_name(row[4])))
    finally:
        workbook.close()
    actual = [(quiz.fixture_date.date(), quiz.home_team, quiz.away_team) for quiz in app.config["FEATURED_QUIZZES"]]
    assert sorted(actual) == sorted(populated)
    assert max(day for day, _, _ in actual).isoformat() == "2026-12-06"
    available = set(app.config["ALL_CLUBS"]) | {
        club for league in app.config["LEAGUES"] for club in league.clubs
    }
    # The owner will supply Como's kit separately.
    assert available - BADGE_FILES.keys() <= {"Como"}
    assert all((STATIC / "img" / "kits" / BADGE_FILES[club]).is_file() for club in available if club != "Como")
    featured_clubs = {club for _, home, away in actual for club in (home, away)}
    assert featured_clubs <= BADGE_FILES.keys()
