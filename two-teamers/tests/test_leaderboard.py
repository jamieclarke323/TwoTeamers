import sqlite3

from app.db import get_db, get_progress, init_db, save_progress
from app.leaderboard import calculate_standings, fan_standing


def create_user() -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("leaderboard@example.com", "test-hash"),
    )
    db.commit()
    return cursor.lastrowid


def create_supporter(email: str, team: str) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO users (email, password_hash, supported_team) VALUES (?, ?, ?)",
        (email, "test-hash", team),
    )
    db.commit()
    return cursor.lastrowid


def save_score(user_id: int, quiz_id: str, correct: int, total: int):
    save_progress(
        user_id,
        quiz_id,
        {
            "solved": [],
            "given_up": False,
            "score_started": True,
            "score_correct": correct,
            "score_total": total,
            "score_frozen": True,
        },
    )


def test_leaderboard_score_defaults(app):
    with app.app_context():
        state = get_progress(1, "quiz-1")
        assert state["score_started"] is False
        assert state["score_correct"] == 0
        assert state["score_total"] == 0
        assert state["score_frozen"] is False


def test_leaderboard_score_persists(app):
    with app.app_context():
        user_id = create_user()
        save_progress(
            user_id,
            "quiz-1",
            {
                "solved": [0, 1],
                "given_up": False,
                "score_started": True,
                "score_correct": 2,
                "score_total": 10,
                "score_frozen": True,
            },
        )
        state = get_progress(user_id, "quiz-1")
        assert state["score_started"] is True
        assert state["score_correct"] == 2
        assert state["score_total"] == 10
        assert state["score_frozen"] is True


def test_answer_tracking_persists_with_progress(app):
    with app.app_context():
        user_id = create_user()
        answer_data = {
            "clues": {"1": ["apps", "goals"]},
            "solve_order": [{"index": 2, "clue_count": 0}, {"index": 1, "clue_count": 2}],
        }
        save_progress(
            user_id,
            "quiz-1",
            {"solved": [1, 2], "given_up": False, "answer_data": answer_data},
        )
        assert get_progress(user_id, "quiz-1")["answer_data"] == answer_data


def test_quiz_reset_style_save_preserves_leaderboard_score(app):
    with app.app_context():
        user_id = create_user()
        save_progress(
            user_id,
            "quiz-1",
            {
                "solved": [0, 1],
                "given_up": False,
                "score_started": True,
                "score_correct": 2,
                "score_total": 10,
                "score_frozen": True,
            },
        )
        save_progress(user_id, "quiz-1", {"solved": [], "given_up": False})
        state = get_progress(user_id, "quiz-1")
        assert state["score_started"] is True
        assert state["score_correct"] == 2
        assert state["score_total"] == 10
        assert state["score_frozen"] is True


def test_clue_freezes_score_before_later_correct_answers(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    first_player = quiz.players[0]
    second_player = quiz.players[1]

    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": first_player.name}
    )
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/clue", json={"types": ["apps"], "index": 1}
    )
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": second_player.name}
    )

    with app.app_context():
        state = get_progress(1, quiz.quiz_id)
        assert state["solved"] == [0, 1]
        assert state["score_correct"] == 1
        assert state["score_total"] == quiz.total_players
        assert state["score_frozen"] is True


def test_reset_freezes_started_leaderboard_score(signed_in_client, app):
    quiz = app.config["QUIZZES"][0]
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    )
    signed_in_client.post(f"/quiz/{quiz.quiz_id}/reset", json={"confirm": True})
    signed_in_client.post(
        f"/quiz/{quiz.quiz_id}/guess", json={"guess": quiz.players[0].name}
    )

    with app.app_context():
        state = get_progress(1, quiz.quiz_id)
        assert state["score_correct"] == 1
        assert state["score_frozen"] is True


def test_team_points_average_fan_scores_across_all_played_fixtures(app):
    arsenal_quizzes = [
        quiz
        for quiz in app.config["QUIZZES"]
        if "Arsenal" in (quiz.home_team, quiz.away_team)
    ]
    unrelated = next(
        quiz
        for quiz in app.config["QUIZZES"]
        if "Arsenal" not in (quiz.home_team, quiz.away_team)
    )
    with app.app_context():
        first = create_supporter("first@example.com", "Arsenal")
        second = create_supporter("second@example.com", "Arsenal")
        save_score(first, arsenal_quizzes[0].quiz_id, 8, 10)
        save_score(first, unrelated.quiz_id, 10, 10)
        save_score(second, arsenal_quizzes[0].quiz_id, 6, 10)

        clubs = [club for league in app.config["LEAGUES"] for club in league.clubs]
        standings, user_averages, users_by_team, scores_by_user = calculate_standings(
            get_db(), app.config["QUIZZES"], clubs
        )
        arsenal = next(row for row in standings if row.team == "Arsenal")
        assert len(standings) == 92
        assert arsenal.points == 75.0
        assert arsenal.scoring_supporters == 2
        assert arsenal.games_played == 3
        assert fan_standing(first, "Arsenal", user_averages, users_by_team, scores_by_user).rank == 1
        assert fan_standing(second, "Arsenal", user_averages, users_by_team, scores_by_user).rank == 2


def test_matchweek_scope_only_uses_that_weeks_games(app):
    arsenal_quizzes = [
        quiz
        for quiz in app.config["QUIZZES"]
        if "Arsenal" in (quiz.home_team, quiz.away_team)
    ]
    first_quiz = arsenal_quizzes[0]
    other_quiz = next(
        quiz for quiz in arsenal_quizzes if quiz.matchweek != first_quiz.matchweek
    )
    with app.app_context():
        user_id = create_supporter("fan@example.com", "Arsenal")
        save_score(user_id, first_quiz.quiz_id, 2, 10)
        save_score(user_id, other_quiz.quiz_id, 10, 10)
        clubs = [club for league in app.config["LEAGUES"] for club in league.clubs]
        standings, *_ = calculate_standings(
            get_db(), app.config["QUIZZES"], clubs, first_quiz.matchweek
        )
        arsenal = next(row for row in standings if row.team == "Arsenal")
        assert arsenal.points == 20.0
        assert arsenal.games_played == 1


def test_existing_progress_table_is_migrated(app):
    legacy_path = app.config["DATABASE"] + ".leaderboard-legacy"
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT,
            password_hash TEXT,
            supported_team TEXT DEFAULT 'Neutral'
        );
        CREATE TABLE progress (
            user_id INTEGER NOT NULL,
            quiz_id TEXT NOT NULL,
            solved_json TEXT NOT NULL DEFAULT '[]',
            given_up INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, quiz_id)
        );
        """
    )
    connection.close()
    app.config["DATABASE"] = legacy_path
    init_db(app)
    connection = sqlite3.connect(legacy_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(progress)")}
    connection.close()
    assert {
        "score_started", "score_correct", "score_total", "score_frozen", "answer_data_json"
    } <= columns


def test_leaderboard_page_shows_users_points_and_rank(signed_in_client, app):
    quiz = next(
        quiz
        for quiz in app.config["QUIZZES"]
        if "Arsenal" in (quiz.home_team, quiz.away_team)
    )
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET supported_team = 'Arsenal' WHERE id = 1")
        db.commit()
        save_score(1, quiz.quiz_id, 8, 10)
    app.config["LEADERBOARD_ENABLED"] = True
    response = signed_in_client.get("/leaderboard")
    assert response.status_code == 200
    assert b"#1" in response.data
    assert b"80.0" in response.data
