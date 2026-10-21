from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, current_app

from .data_loader import QUIZ_TIMEZONE
from .db import get_db

logger = logging.getLogger(__name__)
NOTIFICATION_TITLE = "Today's Two Teamers game is ready to play!"


class PushDeliveryError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _send_web_push(subscription: dict, message: dict, private_key: str) -> None:
    try:
        from pywebpush import WebPushException, webpush
        from requests.exceptions import RequestException
    except ImportError as error:
        raise PushDeliveryError("The pywebpush package is not installed.") from error

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(message),
            ttl=86400,
            vapid_private_key=private_key,
            vapid_claims={"sub": current_app.config["PUSH_VAPID_SUBJECT"]},
        )
    except WebPushException as error:
        status_code = error.response.status_code if error.response else None
        raise PushDeliveryError("The push service rejected the notification.", status_code) from error
    except RequestException as error:
        raise PushDeliveryError("Could not connect to the push service.") from error


def send_daily_notifications(
    app: Flask, now: datetime | None = None
) -> int:
    """Send one notification per subscribed user for a playable supported-team fixture."""
    now = now or datetime.now(QUIZ_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=QUIZ_TIMEZONE)
    else:
        now = now.astimezone(QUIZ_TIMEZONE)
    notification_date = now.date().isoformat()

    with app.app_context():
        playable_by_team = {}
        for quiz in current_app.config["QUIZZES"]:
            if (
                quiz.fixture_date.date() == now.date()
                and quiz.total_players
                and quiz.availability(now) == "playable"
            ):
                playable_by_team.setdefault(quiz.home_team, quiz)
                playable_by_team.setdefault(quiz.away_team, quiz)

        if not playable_by_team:
            return 0

        rows = get_db().execute(
            """SELECT u.id, u.supported_team, s.endpoint, s.subscription_json
               FROM users u
               JOIN push_subscriptions s ON s.user_id = u.id
               WHERE u.supported_team != 'Neutral'
               ORDER BY u.id, s.endpoint"""
        ).fetchall()
        users = {}
        for row in rows:
            quiz = playable_by_team.get(row["supported_team"])
            if quiz is None:
                continue
            users.setdefault(row["id"], (quiz, []))[1].append(row)

        if users:
            private_key_file = current_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"]
            if not private_key_file:
                raise RuntimeError("PUSH_VAPID_PRIVATE_KEY_FILE is not configured.")
            try:
                private_key = Path(private_key_file).read_text(encoding="utf-8")
            except OSError as error:
                raise RuntimeError(
                    "The VAPID private key file could not be read."
                ) from error

        sent_users = 0
        db = get_db()
        for user_id, (quiz, subscriptions) in users.items():
            reservation = db.execute(
                """INSERT OR IGNORE INTO push_notification_sends
                   (user_id, notification_date, quiz_id) VALUES (?, ?, ?)""",
                (user_id, notification_date, quiz.quiz_id),
            )
            db.commit()
            if reservation.rowcount == 0:
                continue

            message = {
                "title": NOTIFICATION_TITLE,
                "body": f"Tap to play {quiz.home_team} vs {quiz.away_team}.",
                "url": f"/quiz/{quiz.quiz_id}",
            }
            successes = 0
            for row in subscriptions:
                try:
                    _send_web_push(
                        json.loads(row["subscription_json"]), message, private_key
                    )
                    successes += 1
                except PushDeliveryError as error:
                    logger.warning(
                        "Push delivery failed for user %s (HTTP %s).",
                        user_id,
                        error.status_code or "unknown",
                    )
                    if error.status_code in (404, 410):
                        db.execute(
                            "DELETE FROM push_subscriptions WHERE endpoint = ?",
                            (row["endpoint"],),
                        )
            if successes:
                sent_users += 1
            else:
                db.execute(
                    """DELETE FROM push_notification_sends
                       WHERE user_id = ? AND notification_date = ?""",
                    (user_id, notification_date),
                )
            db.commit()
        return sent_users
