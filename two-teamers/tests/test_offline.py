from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import time

import pytest

from app import create_app
from app.data_loader import ClubPlayer, League, Quiz, QuizPlayer, QUIZ_TIMEZONE
from app.db import get_db, get_progress
from app.offline import COMBINING_MARKS, SYNC_MAX_AGE, _signer


@pytest.fixture
def offline_app(tmp_path, monkeypatch):
    players = [
        QuizPlayer(name, ClubPlayer(name, "2020", 10, 1, "France", str(index)),
                   ClubPlayer(name, "2021", 20, 2, "France", str(index)))
        for index, name in enumerate(("Jóhann Berg Guðmundsson", "Patrick van Aanholt"))
    ]
    quiz = Quiz(
        "offline-test", "premier-league", 1, 1, datetime.now(QUIZ_TIMEZONE),
        "Ground", "Home", "Away", players,
    )
    monkeypatch.setattr("app.load_game_data", lambda *args: (
        [League("premier-league", "Premier League", ("Home", "Away"), True)],
        [quiz], [], {},
    ))
    return create_app({
        "TESTING": True, "SECRET_KEY": "offline-test-secret",
        "DATABASE": str(tmp_path / "offline.sqlite"), "BYPASS_AVAILABILITY": True,
        "REWARDED_ADS_ENABLED": False,
    })


@pytest.fixture
def offline_client(offline_app):
    return offline_app.test_client()


def _download(client):
    response = client.post("/quiz/offline-test/offline-package")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.get_json()


def _sync(client, package, actions):
    return client.post("/quiz/offline-test/offline-sync", json={
        "token": package["token"], "actions": actions,
    })


def _event(package, seq=1, action="guess", body=None):
    return {
        "seq": seq, "at": package["issuedAt"] + seq, "action": action,
        "body": body if body is not None else {"guess": "Guðmundsson"},
    }


def _state(app, client):
    with client.session_transaction() as browser_session:
        identity = browser_session.get("user_id", browser_session.get("visitor_id"))
    with app.app_context():
        return get_progress(identity, "offline-test")


def test_online_page_still_hides_answers_until_opt_in(offline_client):
    response = offline_client.get("/quiz/offline-test")
    assert b"Play offline" in response.data
    assert b'id="offline-package"' not in response.data
    assert "Guðmundsson".encode() not in response.data
    assert offline_client.post(
        "/quiz/offline-test/guess", json={"guess": "Gudmundsson"}
    ).get_json()["status"] == "correct"


def test_offline_button_is_compact_and_below_answer_box(offline_client):
    page = offline_client.get("/quiz/offline-test").get_data(as_text=True)
    assert page.index('id="guess-input"') < page.index('id="play-offline"') < page.index("</form>")
    assert 'class="button offline-button"' in page
    assert 'id="offline-status"' in page
    snapshot = _download(offline_client)["html"]
    assert 'id="play-offline"' not in snapshot
    assert 'id="guess-input"' in snapshot
    assert 'id="offline-status"' in snapshot


def test_download_contains_matching_clues_assets_and_eight_hour_limit(offline_client):
    downloaded = _download(offline_client)
    package = downloaded["package"]
    assert package["expiresAt"] - package["issuedAt"] == 8 * 60 * 60 * 1000
    assert package["players"][0]["answers"][-1] == "Guðmundsson"
    assert package["players"][0]["clues"]["nationality"] == "🇫🇷 France"
    assert "Bookmark this page" in downloaded["html"]
    assert "/static/js/offline-game.js" in downloaded["assets"]
    assert downloaded["url"] == f"/offline/quiz/offline-test?download={package['id']}"
    for asset in downloaded["assets"]:
        assert offline_client.get(asset).status_code == 200


def test_download_expires_at_game_lock_if_sooner(offline_app, offline_client):
    quiz = offline_app.config["QUIZZES"][0]
    now = datetime.now(QUIZ_TIMEZONE)
    class ShortQuiz(type(quiz)):
        @property
        def lock_at(self):
            return now + timedelta(hours=1)

        def availability(self, now=None):
            return "playable"
    monkey_quiz = ShortQuiz(**vars(quiz))
    offline_app.config["BYPASS_AVAILABILITY"] = False
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = monkey_quiz
    package = _download(offline_client)["package"]
    assert package["expiresAt"] == int(monkey_quiz.lock_at.timestamp() * 1000)
    assert package["expiresAt"] - package["issuedAt"] < 8 * 60 * 60 * 1000


def test_locked_and_empty_games_cannot_be_downloaded(offline_app, offline_client):
    quiz = offline_app.config["QUIZZES"][0]
    offline_app.config["BYPASS_AVAILABILITY"] = False
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(
        quiz, fixture_date=datetime.now(QUIZ_TIMEZONE) + timedelta(days=5)
    )
    assert offline_client.post("/quiz/offline-test/offline-package").status_code == 403
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(quiz, players=[])
    assert offline_client.post("/quiz/offline-test/offline-package").status_code == 409


def test_sync_replays_guesses_not_client_scores_and_is_idempotent(offline_app, offline_client):
    package = _download(offline_client)["package"]
    event = _event(package)
    response = _sync(offline_client, package, [event])
    assert response.get_json()["acknowledged"] == 1
    assert _sync(offline_client, package, [event]).get_json()["acknowledged"] == 1
    state = _state(offline_app, offline_client)
    assert state["solved"] == [0]
    assert state["score_correct"] == 1
    assert len(state["answer_data"]["solve_order"]) == 1


def test_sync_preserves_clue_scoring_giveup_and_reset(offline_app, offline_client):
    package = _download(offline_client)["package"]
    actions = [
        _event(package, 1),
        _event(package, 2, "clue", {"types": ["initials"], "index": 1}),
        _event(package, 3, "guess", {"guess": "Aanholt"}),
        _event(package, 4, "giveup", {"confirm": True}),
    ]
    assert _sync(offline_client, package, actions).status_code == 200
    state = _state(offline_app, offline_client)
    assert state["solved"] == [0, 1]
    assert state["score_correct"] == 1
    assert state["score_frozen"] is True
    assert state["given_up"] is True
    assert state["answer_data"]["clues"] == {"1": ["initials"]}
    assert _sync(offline_client, package, [_event(package, 5, "reset", {})]).status_code == 200
    state = _state(offline_app, offline_client)
    assert state["solved"] == []
    assert state["score_correct"] == 1


def test_sync_rejects_expired_actions_and_rolls_back_entire_batch(offline_app, offline_client):
    package = _download(offline_client)["package"]
    invalid = _event(package, 2, "giveup", {"confirm": True})
    invalid["at"] = package["expiresAt"]
    assert _sync(offline_client, package, [_event(package), invalid]).status_code == 400
    assert _state(offline_app, offline_client)["solved"] == []
    assert _sync(offline_client, package, [_event(package)]).status_code == 200


def test_sync_rejects_wrong_identity_tampering_and_changed_answers(offline_app, offline_client):
    package = _download(offline_client)["package"]
    other = offline_app.test_client()
    assert _sync(other, package, [_event(package)]).status_code == 403
    tampered = deepcopy(package)
    tampered["token"] += "tampered"
    assert _sync(offline_client, tampered, [_event(package)]).status_code == 403
    quiz = offline_app.config["QUIZZES"][0]
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(quiz, players=quiz.players[:1])
    assert _sync(offline_client, package, [_event(package)]).status_code == 409


def test_sync_does_not_overwrite_progress_from_another_page(offline_app, offline_client):
    package = _download(offline_client)["package"]
    offline_client.post("/quiz/offline-test/guess", json={"guess": "Aanholt"})
    assert _sync(offline_client, package, [_event(package)]).status_code == 409
    assert _state(offline_app, offline_client)["solved"] == [1]


def test_ad_gated_clues_are_not_replayed_offline(offline_app, offline_client):
    offline_app.config["REWARDED_ADS_ENABLED"] = True
    downloaded = _download(offline_client)
    assert "adsbygoogle.js" not in downloaded["html"]
    package = downloaded["package"]
    event = _event(package, action="clue", body={"types": ["years"], "index": 0})
    assert _sync(offline_client, package, [event]).status_code == 400
    assert _state(offline_app, offline_client)["answer_data"]["clues"] == {}


def test_registered_user_sync_stays_with_account_and_offline_html_has_no_email(offline_app, offline_client):
    with offline_app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (id, email, password_hash) VALUES (1, 'fan@example.com', 'hash')")
        db.commit()
    with offline_client.session_transaction() as browser_session:
        browser_session["user_id"] = 1
    downloaded = _download(offline_client)
    assert "fan@example.com" not in downloaded["html"]
    package = downloaded["package"]
    assert _sync(offline_client, package, [_event(package)]).status_code == 200
    with offline_app.app_context():
        assert get_progress(1, "offline-test")["solved"] == [0]


def test_reconnect_can_sync_actions_after_play_window_ends(offline_app, offline_client, monkeypatch):
    package = _download(offline_client)["package"]
    quiz = offline_app.config["QUIZZES"][0]
    offline_app.config["BYPASS_AVAILABILITY"] = False
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(
        quiz, fixture_date=quiz.fixture_date - timedelta(days=10)
    )
    reconnect_time = time.time() + 9 * 60 * 60
    monkeypatch.setattr("time.time", lambda: reconnect_time)
    assert _sync(offline_client, package, [_event(package)]).status_code == 200
    assert _state(offline_app, offline_client)["solved"] == [0]


def test_token_stops_syncing_after_seven_days(offline_client, monkeypatch):
    package = _download(offline_client)["package"]
    reconnect_time = time.time() + SYNC_MAX_AGE + 1
    monkeypatch.setattr("time.time", lambda: reconnect_time)
    response = _sync(offline_client, package, [_event(package)])
    assert response.status_code == 403
    assert "expired" in response.get_json()["message"]


@pytest.mark.parametrize("changes", [
    {"seq": 2},
    {"seq": True},
    {"at": 0},
    {"action": "clue-unlock"},
    {"body": {"guess": ["Guðmundsson"]}},
    {"body": {"guess": "x" * 501}},
    {"action": "clue", "body": {"types": ["apps"], "index": 0}},
    {"action": "giveup", "body": {"confirm": False}},
])
def test_malformed_actions_are_rejected_without_changing_progress(
    offline_app, offline_client, changes
):
    package = _download(offline_client)["package"]
    event = {**_event(package), **changes}
    assert _sync(offline_client, package, [event]).status_code == 400
    assert _state(offline_app, offline_client)["solved"] == []


def test_actions_cannot_be_dated_in_the_future(offline_client):
    package = _download(offline_client)["package"]
    event = _event(package)
    event["at"] = package["issuedAt"] + 60 * 60 * 1000
    assert _sync(offline_client, package, [event]).status_code == 400


def test_sync_accepts_partial_batches_with_duplicate_prefix(offline_app, offline_client):
    package = _download(offline_client)["package"]
    first = _event(package)
    second = _event(package, 2, body={"guess": "Aanholt"})
    assert _sync(offline_client, package, [first]).get_json()["acknowledged"] == 1
    assert _sync(offline_client, package, [first, second]).get_json()["acknowledged"] == 2
    state = _state(offline_app, offline_client)
    assert state["solved"] == [0, 1]
    assert state["score_correct"] == 2


def test_signed_window_cannot_be_extended_by_client(offline_app, offline_client):
    package = _download(offline_client)["package"]
    with offline_app.app_context():
        claims = _signer().loads(package["token"])
    assert claims["expiresAt"] == package["expiresAt"]
    event = _event(package)
    event["at"] = package["expiresAt"] + 1
    package["expiresAt"] += 60 * 60 * 1000
    assert _sync(offline_client, package, [event]).status_code == 400


def test_download_includes_python_combining_classes_for_browser_parity(offline_client):
    package = _download(offline_client)["package"]
    assert package["combiningMarks"] == COMBINING_MARKS
    assert "\u0301" in COMBINING_MARKS
    assert "\u034f" not in COMBINING_MARKS


def test_sync_script_runs_even_when_game_is_locked(offline_app, offline_client):
    offline_app.config["BYPASS_AVAILABILITY"] = False
    quiz = offline_app.config["QUIZZES"][0]
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(
        quiz, fixture_date=quiz.fixture_date - timedelta(days=10)
    )
    page = offline_client.get("/quiz/offline-test")
    assert b"/static/js/offline-sync.js" in page.data


def test_service_worker_remains_push_capable(offline_client):
    response = offline_client.get("/service-worker.js")
    assert response.status_code == 200
    assert b'SAVE_OFFLINE_GAME' in response.data
    assert b'addEventListener("push"' in response.data
    assert response.headers["Service-Worker-Allowed"] == "/"


def test_online_actions_lock_progress_before_reading(offline_app, offline_client, monkeypatch):
    from app import routes

    original = routes.get_progress
    reads = []

    def locked_progress(*args):
        reads.append(get_db().in_transaction)
        return original(*args)

    monkeypatch.setattr(routes, "get_progress", locked_progress)
    assert offline_client.post(
        "/quiz/offline-test/guess", json={"guess": "Gudmundsson"}
    ).status_code == 200
    offline_app.config["REWARDED_ADS_ENABLED"] = True
    assert offline_client.post("/quiz/offline-test/clue-unlock").status_code == 200
    assert reads == [True, True]


def test_online_and_offline_sequences_produce_identical_progress(offline_app, offline_client):
    package = _download(offline_client)["package"]
    online = offline_app.test_client()
    actions = [
        ("exact", {"guess": "Gudmundson"}),
        ("guess", {"guess": "Wrong Name"}),
        ("guess", {"guess": "Gudmanson"}),
        ("guess", {"guess": "Gudmundson"}),
        ("clue", {"types": ["initials", "years"], "index": 1}),
        ("guess", {"guess": "Aanholt"}),
        ("giveup", {"confirm": True}),
        ("reset", {}),
    ]
    for action, body in actions:
        assert online.post(f"/quiz/offline-test/{action}", json=body).status_code == 200
    assert _sync(offline_client, package, [
        _event(package, index, action, body)
        for index, (action, body) in enumerate(actions, start=1)
    ]).status_code == 200
    assert _state(offline_app, online) == _state(offline_app, offline_client)


def test_individual_giveup_keeps_remaining_scoring_and_shares_cross(offline_app, offline_client):
    url = "/quiz/offline-test"
    result = offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True})
    assert result.status_code == 200
    assert result.json["status"] == "answer_revealed"
    assert result.json["player"]["name"] == "Jóhann Berg Guðmundsson"
    assert result.json["solved_count"] == 0
    assert result.json["completed"] is False
    state = _state(offline_app, offline_client)
    assert state["answer_data"]["revealed"] == [0]
    assert state["score_correct"] == 0
    assert state["score_started"] is True
    assert state["score_frozen"] is False
    assert state["given_up"] is False
    repeated = offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True})
    assert repeated.status_code == 200
    assert _state(offline_app, offline_client) == state
    page = offline_client.get(url).get_data(as_text=True)
    assert "❌ Jóhann Berg Guðmundsson" in page
    assert 'id="give-up-answer"' in page
    assert offline_client.post(f"{url}/guess", json={"guess": "Guðmundsson"}).json["status"] == "wrong"
    final = offline_client.post(f"{url}/guess", json={"guess": "Aanholt"}).json
    assert final["completed"] is True
    assert final["solved_count"] == 1
    assert "TWO TEAMERS 1/2" in final["share_text"]
    assert "❌ 🟢" in final["share_text"]
    state = _state(offline_app, offline_client)
    assert state["solved"] == [1]
    assert state["score_correct"] == 1
    assert state["score_frozen"] is True
    page = offline_client.get(url).get_data(as_text=True)
    assert 'id="guess-input" type="text" placeholder="Type a surname..." autocomplete="off" disabled' in page


def test_individual_giveup_as_last_answer_finishes_game(offline_client):
    url = "/quiz/offline-test"
    offline_client.post(f"{url}/guess", json={"guess": "Aanholt"})
    final = offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True}).json
    assert final["completed"] is True
    assert "❌ 🟢" in final["share_text"]
    assert "TWO TEAMERS 1/2" in final["share_text"]


@pytest.mark.parametrize("body", [
    {"index": 0}, {"index": 0, "confirm": False}, {"index": 0, "confirm": "yes"},
    {"index": -1, "confirm": True}, {"index": 2, "confirm": True},
    {"index": True, "confirm": True}, {"index": "0", "confirm": True},
])
def test_individual_giveup_requires_valid_index_and_confirmation(offline_app, offline_client, body):
    assert offline_client.post("/quiz/offline-test/giveup-answer", json=body).status_code == 400
    assert _state(offline_app, offline_client)["score_started"] is False


def test_individual_giveup_does_not_replace_correct_or_globally_revealed_answers(offline_client):
    url = "/quiz/offline-test"
    offline_client.post(f"{url}/guess", json={"guess": "Aanholt"})
    assert offline_client.post(f"{url}/giveup-answer", json={"index": 1, "confirm": True}).status_code == 409
    offline_client.post(f"{url}/giveup", json={"confirm": True})
    assert offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True}).status_code == 409


def test_revealed_answers_are_excluded_from_clues_and_reset_clears_them(offline_app, offline_client):
    url = "/quiz/offline-test"
    offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True})
    clues = offline_client.post(f"{url}/clue", json={"types": ["initials"], "index": "all"}).json
    assert [clue["index"] for clue in clues["clues"]] == [1]
    offline_client.post(f"{url}/reset", json={})
    assert "revealed" not in _state(offline_app, offline_client)["answer_data"]
    assert offline_client.post(f"{url}/guess", json={"guess": "Guðmundsson"}).json["status"] == "correct"
    assert _state(offline_app, offline_client)["score_correct"] == 0


def test_individual_giveup_works_with_ad_gated_clues_and_syncs(offline_app, offline_client):
    offline_app.config["REWARDED_ADS_ENABLED"] = True
    package = _download(offline_client)["package"]
    actions = [
        _event(package, 1, "giveup-answer", {"index": 0, "confirm": True}),
        _event(package, 2, "guess", {"guess": "Aanholt"}),
    ]
    response = _sync(offline_client, package, actions)
    assert response.status_code == 200
    assert response.json["acknowledged"] == 2
    assert _sync(offline_client, package, actions).status_code == 200
    state = _state(offline_app, offline_client)
    assert state["score_correct"] == 1
    assert state["solved"] == [1]
    assert state["answer_data"]["revealed"] == [0]


def test_offline_refresh_uses_current_template_without_extending_download(offline_app, offline_client):
    downloaded = _download(offline_client)
    package = downloaded["package"]
    _sync(offline_client, package, [_event(package, 1, "giveup-answer", {"index": 0, "confirm": True})])
    response = offline_client.post("/quiz/offline-test/offline-refresh", json={"token": package["token"]})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    refreshed = response.json
    assert refreshed["url"] == downloaded["url"]
    assert refreshed["package"]["expiresAt"] == package["expiresAt"]
    assert refreshed["package"]["issuedAt"] == package["issuedAt"]
    assert refreshed["package"]["token"] == package["token"]
    assert refreshed["package"]["state"]["answer_data"]["revealed"] == [0]
    assert "<small>1999/2000 season onwards only.</small>" in refreshed["html"]
    assert 'id="give-up-answer"' in refreshed["html"]
    assert "❌ Jóhann Berg Guðmundsson" in refreshed["html"]
    with offline_app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM offline_sessions").fetchone()[0] == 1


def test_offline_refresh_rejects_other_identity_changed_answers_and_expiry(offline_app, offline_client, monkeypatch):
    package = _download(offline_client)["package"]
    path = "/quiz/offline-test/offline-refresh"
    assert offline_client.post(path, json={}).status_code == 400
    assert offline_client.post(path, json={"token": "bad"}).status_code == 403
    assert offline_app.test_client().post(path, json={"token": package["token"]}).status_code == 403
    quiz = offline_app.config["QUIZZES_BY_ID"]["offline-test"]
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = replace(quiz, players=quiz.players[:1])
    assert offline_client.post(path, json={"token": package["token"]}).status_code == 409
    offline_app.config["QUIZZES_BY_ID"]["offline-test"] = quiz
    monkeypatch.setattr("time.time", lambda: package["expiresAt"] / 1000 + 1)
    assert offline_client.post(path, json={"token": package["token"]}).status_code == 410


def test_refresh_refuses_to_replace_progress_changed_online(offline_app, offline_client):
    package = _download(offline_client)["package"]
    offline_client.post("/quiz/offline-test/guess", json={"guess": "Aanholt"})
    response = offline_client.post("/quiz/offline-test/offline-refresh", json={"token": package["token"]})
    assert response.status_code == 409
    assert _state(offline_app, offline_client)["solved"] == [1]


def test_giving_up_on_every_answer_finishes_with_zero_found(offline_app, offline_client):
    url = "/quiz/offline-test/giveup-answer"
    offline_client.post(url, json={"index": 1, "confirm": True})
    final = offline_client.post(url, json={"index": 0, "confirm": True}).json
    assert final["completed"] is True
    assert final["solved_count"] == 0
    assert "TWO TEAMERS 0/2" in final["share_text"]
    assert "❌ ❌" in final["share_text"]
    assert _state(offline_app, offline_client)["score_correct"] == 0
    assert _state(offline_app, offline_client)["score_frozen"] is True


def test_clue_then_giveup_keeps_cross_instead_of_clue_colour(offline_client):
    url = "/quiz/offline-test"
    offline_client.post(f"{url}/clue", json={"index": 0, "types": ["initials"]})
    offline_client.post(f"{url}/giveup-answer", json={"index": 0, "confirm": True})
    final = offline_client.post(f"{url}/guess", json={"guess": "Aanholt"}).json
    assert "❌ 🟢" in final["share_text"]


@pytest.mark.parametrize("guess_first", [False, True])
def test_whole_quiz_giveup_marks_only_unguessed_cards_as_revealed(offline_client, guess_first):
    from html.parser import HTMLParser

    class Cards(HTMLParser):
        def __init__(self):
            super().__init__()
            self.classes = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "button" and "data-index" in attrs:
                self.classes[int(attrs["data-index"])] = attrs["class"].split()

    if guess_first:
        offline_client.post("/quiz/offline-test/guess", json={"guess": "Aanholt"})
    offline_client.post("/quiz/offline-test/giveup", json={"confirm": True})
    pages = [
        offline_client.get("/quiz/offline-test").get_data(as_text=True),
        _download(offline_client)["html"],
    ]
    for page in pages:
        cards = Cards()
        cards.feed(page)
        assert "revealed" in cards.classes[0]
        assert ("revealed" in cards.classes[1]) is not guess_first
        assert all("found" in classes for classes in cards.classes.values())
