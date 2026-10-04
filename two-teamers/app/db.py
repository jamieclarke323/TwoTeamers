from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    supported_team TEXT NOT NULL DEFAULT 'Neutral',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL,
    quiz_id TEXT NOT NULL,
    solved_json TEXT NOT NULL DEFAULT '[]',
    given_up INTEGER NOT NULL DEFAULT 0,
    score_started INTEGER NOT NULL DEFAULT 0,
    score_correct INTEGER NOT NULL DEFAULT 0,
    score_total INTEGER NOT NULL DEFAULT 0,
    score_frozen INTEGER NOT NULL DEFAULT 0,
    answer_data_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, quiz_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS guest_progress (
    visitor_id TEXT NOT NULL,
    quiz_id TEXT NOT NULL,
    solved_json TEXT NOT NULL DEFAULT '[]',
    given_up INTEGER NOT NULL DEFAULT 0,
    score_started INTEGER NOT NULL DEFAULT 0,
    score_correct INTEGER NOT NULL DEFAULT 0,
    score_total INTEGER NOT NULL DEFAULT 0,
    score_frozen INTEGER NOT NULL DEFAULT 0,
    answer_data_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (visitor_id, quiz_id)
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app: Flask) -> None:
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.executescript(SCHEMA)
    user_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "supported_team" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN supported_team TEXT NOT NULL DEFAULT 'Neutral'"
        )
    for table in ("progress", "guest_progress"):
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in (
            ("score_started", "INTEGER NOT NULL DEFAULT 0"),
            ("score_correct", "INTEGER NOT NULL DEFAULT 0"),
            ("score_total", "INTEGER NOT NULL DEFAULT 0"),
            ("score_frozen", "INTEGER NOT NULL DEFAULT 0"),
            ("answer_data_json", "TEXT NOT NULL DEFAULT '{}'"),
        ):
            if column not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    connection.commit()
    connection.close()


def _progress_table(identity: int | str) -> tuple[str, str]:
    if isinstance(identity, int):
        return "progress", "user_id"
    return "guest_progress", "visitor_id"


def get_progress(user_id: int | str, quiz_id: str) -> dict:
    table, identity_column = _progress_table(user_id)
    row = get_db().execute(
        f"""SELECT solved_json, given_up, score_started, score_correct,
               score_total, score_frozen, answer_data_json
            FROM {table} WHERE {identity_column} = ? AND quiz_id = ?""",
        (user_id, quiz_id),
    ).fetchone()
    if row is None:
        return {
            "solved": [],
            "given_up": False,
            "score_started": False,
            "score_correct": 0,
            "score_total": 0,
            "score_frozen": False,
            "answer_data": {"clues": {}, "solve_order": []},
        }
    return {
        "solved": json.loads(row["solved_json"]),
        "given_up": bool(row["given_up"]),
        "score_started": bool(row["score_started"]),
        "score_correct": row["score_correct"],
        "score_total": row["score_total"],
        "score_frozen": bool(row["score_frozen"]),
        "answer_data": json.loads(row["answer_data_json"] or "{}"),
    }


def save_progress(user_id: int | str, quiz_id: str, state: dict) -> None:
    db = get_db()
    table, identity_column = _progress_table(user_id)
    existing = db.execute(
        f"""SELECT score_started, score_correct, score_total, score_frozen,
               answer_data_json
            FROM {table} WHERE {identity_column} = ? AND quiz_id = ?""",
        (user_id, quiz_id),
    ).fetchone()
    score_started = state.get("score_started", existing["score_started"] if existing else 0)
    score_correct = state.get("score_correct", existing["score_correct"] if existing else 0)
    score_total = state.get("score_total", existing["score_total"] if existing else 0)
    score_frozen = state.get("score_frozen", existing["score_frozen"] if existing else 0)
    answer_data = state.get(
        "answer_data",
        json.loads(existing["answer_data_json"] or "{}") if existing else {"clues": {}, "solve_order": []},
    )
    db.execute(
        f"""INSERT INTO {table} (
               {identity_column}, quiz_id, solved_json, given_up, score_started,
               score_correct, score_total, score_frozen, answer_data_json, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT({identity_column}, quiz_id) DO UPDATE SET
             solved_json = excluded.solved_json,
             given_up = excluded.given_up,
             score_started = excluded.score_started,
             score_correct = excluded.score_correct,
             score_total = excluded.score_total,
             score_frozen = excluded.score_frozen,
             answer_data_json = excluded.answer_data_json,
             updated_at = CURRENT_TIMESTAMP""",
        (
            user_id,
            quiz_id,
            json.dumps(state["solved"]),
            int(state["given_up"]),
            int(bool(score_started)),
            int(score_correct),
            int(score_total),
            int(bool(score_frozen)),
            json.dumps(answer_data),
        ),
    )
    db.commit()


def progress_counts(user_id: int | str) -> dict[str, tuple[int, bool]]:
    table, identity_column = _progress_table(user_id)
    rows = get_db().execute(
        f"SELECT quiz_id, solved_json, given_up FROM {table} WHERE {identity_column} = ?",
        (user_id,),
    ).fetchall()
    return {row["quiz_id"]: (len(json.loads(row["solved_json"])), bool(row["given_up"])) for row in rows}


def transfer_guest_progress(visitor_id: str, user_id: int) -> None:
    db = get_db()
    db.execute(
        """INSERT INTO progress (
               user_id, quiz_id, solved_json, given_up, score_started,
               score_correct, score_total, score_frozen, answer_data_json, updated_at
           ) SELECT ?, quiz_id, solved_json, given_up, score_started,
                    score_correct, score_total, score_frozen, answer_data_json, updated_at
             FROM guest_progress WHERE visitor_id = ?
           ON CONFLICT(user_id, quiz_id) DO NOTHING""",
        (user_id, visitor_id),
    )
    db.execute("DELETE FROM guest_progress WHERE visitor_id = ?", (visitor_id,))
    db.commit()
