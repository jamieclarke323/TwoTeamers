import hashlib
import json
import time
import unicodedata
from datetime import datetime, timedelta
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .data_loader import QUIZ_TIMEZONE
from .db import get_db, get_progress, save_progress
from .gameplay import apply_action, public_player

bp = Blueprint("offline", __name__)
OFFLINE_HOURS = 8
SYNC_MAX_AGE = 7 * 24 * 60 * 60
# Python removes nonzero combining classes, not every Unicode mark character.
COMBINING_MARKS = "".join(chr(code) for code in range(0x110000) if unicodedata.combining(chr(code)))


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _quiz_version(quiz):
    return _hash({
        "home": quiz.home_team, "away": quiz.away_team,
        "players": [
            (vars(player.home), vars(player.away), player.name, player.acceptable_answers)
            for player in quiz.players
        ],
    })


def _signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="offline-quiz-v1")


@bp.post("/quiz/<quiz_id>/offline-package")
def download_quiz(quiz_id):
    from .routes import _guard_quiz, _progress_identity, _render_quiz

    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    identity = _progress_identity()
    now = datetime.now(QUIZ_TIMEZONE)
    expires = now + timedelta(hours=OFFLINE_HOURS)
    if not current_app.config["BYPASS_AVAILABILITY"]:
        expires = min(expires, quiz.lock_at)
    session_id = str(uuid4())
    issued_at = int(now.timestamp() * 1000)
    expires_at = int(expires.timestamp() * 1000)
    owner = f"{type(identity).__name__}:{identity}"
    state = get_progress(identity, quiz_id)
    claims = {
        "id": session_id, "owner": owner, "quiz": quiz_id,
        "version": _quiz_version(quiz), "issuedAt": issued_at, "expiresAt": expires_at,
        "adsEnabled": current_app.config["REWARDED_ADS_ENABLED"],
    }
    package = {
        "id": session_id, "quizId": quiz_id, "home": quiz.home_team, "away": quiz.away_team,
        "issuedAt": issued_at, "expiresAt": expires_at, "token": _signer().dumps(claims),
        "adsEnabled": claims["adsEnabled"], "state": state,
        "combiningMarks": COMBINING_MARKS,
        "players": [
            {
                **public_player(quiz, player, index),
                "answers": player.acceptable_answers,
                "clues": {
                    kind: player.clue_value(kind, quiz.home_team, quiz.away_team)
                    for kind in ("years", "initials", "nationality")
                    if kind != "nationality" or player.has_nationality
                },
            }
            for index, player in enumerate(quiz.players)
        ],
    }
    db = get_db()
    db.execute("DELETE FROM offline_sessions WHERE created_at < ?", (int(time.time()) - SYNC_MAX_AGE,))
    db.execute(
        """INSERT INTO offline_sessions (id, identity, quiz_id, state_hash, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, owner, quiz_id, _hash(state), int(time.time())),
    )
    db.commit()
    response = jsonify({
        "package": package,
        "html": _render_quiz(quiz, offline_package=package),
        "url": url_for("offline.offline_page", quiz_id=quiz_id, download=session_id),
        "assets": [
            url_for("static", filename=filename) for filename in (
                "css/style.css", "js/quiz.js", "js/offline-game.js",
                "js/offline-storage.js", "js/offline-sync.js", "js/offline-quiz.js",
                "manifest.webmanifest", "img/two-teamers-app-icon-192.png",
                "img/apple-touch-icon.png",
            )
        ],
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/offline/quiz/<quiz_id>")
def offline_page(quiz_id):
    return redirect(url_for("main.quiz_page", quiz_id=quiz_id))


@bp.post("/quiz/<quiz_id>/offline-sync")
def sync_quiz(quiz_id):
    from .routes import _progress_identity

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("token"), str):
        return jsonify({"message": "Invalid offline session."}), 400
    try:
        claims = _signer().loads(data["token"], max_age=SYNC_MAX_AGE)
    except BadSignature:
        return jsonify({"message": "Offline sync has expired. Your local progress has not been uploaded."}), 403
    identity = _progress_identity()
    owner = f"{type(identity).__name__}:{identity}"
    if claims["owner"] != owner or claims["quiz"] != quiz_id:
        return jsonify({"message": "Sign in with the account used to download this game before syncing."}), 403
    quiz = current_app.config["QUIZZES_BY_ID"].get(quiz_id)
    if quiz is None or claims["version"] != _quiz_version(quiz):
        return jsonify({"message": "This game's answers have changed. Offline progress cannot be synced."}), 409
    actions = data.get("actions")
    if not isinstance(actions, list) or len(actions) > 500:
        return jsonify({"message": "Invalid offline action batch."}), 400
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        record = db.execute("SELECT * FROM offline_sessions WHERE id = ?", (claims["id"],)).fetchone()
        if record is None:
            db.rollback()
            return jsonify({"message": "This offline session is no longer available for sync."}), 410
        state = get_progress(identity, quiz_id)
        if record["state_hash"] != _hash(state):
            db.rollback()
            return jsonify({"message": "Progress changed on another page or device. Offline progress was kept locally, not overwritten."}), 409
        acknowledged = record["acknowledged"]
        last_at = record["last_action_at"]
        for event in actions:
            if not isinstance(event, dict):
                raise ValueError("Invalid offline action.")
            seq, at = event.get("seq"), event.get("at")
            if type(seq) is not int or type(at) is not int:
                raise ValueError("Invalid offline action sequence.")
            if seq <= acknowledged:
                continue
            if (seq != acknowledged + 1 or not claims["issuedAt"] <= at < claims["expiresAt"]
                    or at < last_at or at > int(time.time() * 1000) + 60_000):
                raise ValueError("Offline actions must be ordered and within the downloaded play window.")
            action, body = event.get("action"), event.get("body")
            if action not in ("guess", "exact", "clue", "giveup", "reset") or not isinstance(body, dict):
                raise ValueError("Invalid offline game action.")
            if action in ("guess", "exact") and (
                not isinstance(body.get("guess"), str) or len(body["guess"]) > 500
            ):
                raise ValueError("Invalid offline guess.")
            if action == "clue":
                if claims["adsEnabled"] or current_app.config["REWARDED_ADS_ENABLED"]:
                    raise ValueError("Ad-gated clues cannot be revealed offline.")
                if not isinstance(body.get("types"), list) or any(
                    kind not in ("years", "initials", "nationality") for kind in body["types"]
                ):
                    raise ValueError("Invalid offline clue.")
            result, status = apply_action(quiz, state, action, body)
            if status != 200:
                raise ValueError(result.get("message", "Invalid offline action."))
            acknowledged = seq
            last_at = at
        save_progress(identity, quiz_id, state, commit=False)
        db.execute(
            "UPDATE offline_sessions SET state_hash = ?, acknowledged = ?, last_action_at = ? WHERE id = ?",
            (_hash(state), acknowledged, last_at, claims["id"]),
        )
        db.commit()
    except ValueError as error:
        db.rollback()
        return jsonify({"message": str(error)}), 400
    except Exception:
        db.rollback()
        raise
    return jsonify({"acknowledged": acknowledged})
