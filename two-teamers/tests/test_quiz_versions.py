import json
from dataclasses import replace
from datetime import datetime

from flask import Flask

from app.data_loader import ClubPlayer, Quiz, QuizPlayer, QUIZ_TIMEZONE
from app.db import (
    _answer_fingerprint,
    close_db,
    get_db,
    get_progress,
    init_db,
    save_progress,
    sync_quiz_progress,
)


def _quiz(quiz_id="test", player_id="first"):
    player = ClubPlayer("Same Name", "2020", 10, 1, player_id=player_id)
    return Quiz(
        quiz_id, "test", 1, 1, datetime(2026, 10, 22, tzinfo=QUIZ_TIMEZONE),
        "", "Home", "Away", [QuizPlayer(player.name, player, player)],
    )


def _app(tmp_path):
    app = Flask(__name__)
    app.config["DATABASE"] = str(tmp_path / "progress.sqlite")
    init_db(app)
    app.teardown_appcontext(close_db)
    return app


def _save_both(quiz):
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO users (id, email, password_hash) VALUES (1, 'test@example.com', 'hash')"
    )
    db.commit()
    state = {
        "solved": [0],
        "given_up": False,
        "score_started": True,
        "score_correct": 1,
        "score_total": 1,
        "score_frozen": True,
        "answer_data": {"clues": {"0": ["years"]}},
    }
    save_progress(1, quiz.quiz_id, state)
    save_progress("visitor", quiz.quiz_id, state)


def test_unchanged_quiz_preserves_progress_and_clues(tmp_path):
    app = _app(tmp_path)
    quiz = _quiz()
    with app.app_context():
        sync_quiz_progress([quiz])
        _save_both(quiz)
        sync_quiz_progress([quiz])
        for identity in (1, "visitor"):
            assert get_progress(identity, quiz.quiz_id)["solved"] == [0]
            assert get_progress(identity, quiz.quiz_id)["answer_data"]["clues"] == {"0": ["years"]}


def test_changed_identity_resets_only_affected_quiz_even_if_name_is_unchanged(tmp_path):
    app = _app(tmp_path)
    first = _quiz()
    untouched = _quiz("untouched")
    with app.app_context():
        sync_quiz_progress([first, untouched])
        _save_both(first)
        _save_both(untouched)
        sync_quiz_progress([_quiz(player_id="second"), untouched])
        for identity in (1, "visitor"):
            state = get_progress(identity, first.quiz_id)
            assert state["solved"] == []
            assert state["score_started"] is False
            assert state["answer_data"]["clues"] == {}
            assert get_progress(identity, untouched.quiz_id)["solved"] == [0]


def test_removed_answers_reset_progress(tmp_path):
    app = _app(tmp_path)
    quiz = _quiz()
    with app.app_context():
        sync_quiz_progress([quiz])
        _save_both(quiz)
        sync_quiz_progress([replace(quiz, players=[])])
        assert get_progress(1, quiz.quiz_id)["solved"] == []
        assert get_progress("visitor", quiz.quiz_id)["solved"] == []


def test_first_migration_uses_pre_player_id_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "legacy_quiz_answers.json"
    baseline.write_text(json.dumps({"answers": {
        "changed": _answer_fingerprint(["Removed Player", "Same Name"]),
        "unchanged": _answer_fingerprint(["Same Name"]),
    }}), encoding="utf-8")
    monkeypatch.setattr("app.db.LEGACY_QUIZ_ANSWERS_PATH", baseline)
    app = _app(tmp_path)
    changed = _quiz("changed")
    unchanged = _quiz("unchanged")
    with app.app_context():
        _save_both(changed)
        _save_both(unchanged)
        sync_quiz_progress([changed, unchanged])
        for identity in (1, "visitor"):
            assert get_progress(identity, "changed")["solved"] == []
            assert get_progress(identity, "unchanged")["solved"] == [0]
        _save_both(changed)
        sync_quiz_progress([changed, unchanged])
        assert get_progress(1, "changed")["solved"] == [0]
