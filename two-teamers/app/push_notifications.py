from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, time as wall_time, timedelta
from pathlib import Path

from flask import Flask, current_app

from .data_loader import QUIZ_TIMEZONE
from .db import get_db

logger = logging.getLogger(__name__)
DAILY_GAME_SEND_TIME = wall_time(7, 31)
MY_TEAM_SEND_TIME = wall_time(7, 45)
MAX_DELIVERY_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (0.5, 1.0)
STALE_DELIVERY_MINUTES = 15
TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
INVALID_SUBSCRIPTION_STATUS_CODES = {404, 410}
DAILY_GAME_TITLE = "Today's Two Teamers game is ready to play!"
MY_TEAM_TITLE = "Your team has a Two Teamers game!"


class PushDeliveryError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _send_web_push(subscription: dict, message: dict, private_key: str) -> None:
    try:
        from py_vapid import Vapid
        from pywebpush import WebPushException, webpush
        from requests.exceptions import RequestException
    except ImportError as error:
        raise RuntimeError("The pywebpush package is not installed.") from error

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(message),
            ttl=86400,
            vapid_private_key=Vapid.from_pem(private_key.encode("utf-8")),
            vapid_claims={"sub": current_app.config["PUSH_VAPID_SUBJECT"]},
        )
    except WebPushException as error:
        status_code = (
            error.response.status_code if error.response is not None else None
        )
        raise PushDeliveryError(
            "The push service rejected the notification.", status_code
        ) from error
    except RequestException as error:
        raise PushDeliveryError("Could not connect to the push service.") from error


def _normalise_now(now: datetime | None) -> datetime:
    now = now or datetime.now(QUIZ_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=QUIZ_TIMEZONE)
    return now.astimezone(QUIZ_TIMEZONE)


def _in_send_window(category: str, now: datetime) -> bool:
    scheduled_time = {
        "daily_game": DAILY_GAME_SEND_TIME,
        "my_team": MY_TEAM_SEND_TIME,
    }[category]
    window_minutes = int(current_app.config["PUSH_SEND_WINDOW_MINUTES"])
    if window_minutes <= 0:
        raise ValueError("PUSH_SEND_WINDOW_MINUTES must be greater than zero.")
    scheduled_at = datetime.combine(now.date(), scheduled_time, tzinfo=QUIZ_TIMEZONE)
    delay = now - scheduled_at
    return timedelta(0) <= delay < timedelta(minutes=window_minutes)


def _fixture_key(quiz) -> tuple[str, str, str]:
    return (
        quiz.fixture_date.date().isoformat(),
        *sorted((quiz.home_team.casefold(), quiz.away_team.casefold())),
    )


def _load_private_key() -> str:
    private_key_file = current_app.config["PUSH_VAPID_PRIVATE_KEY_FILE"]
    if not private_key_file:
        raise RuntimeError("PUSH_VAPID_PRIVATE_KEY_FILE is not configured.")
    try:
        return Path(private_key_file).read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError("The VAPID private key file could not be read.") from error


def _endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def _record_failure(
    db,
    delivery_id: int,
    *,
    status: str,
    status_code: int | None,
    error: str,
) -> None:
    db.execute(
        """UPDATE push_notification_deliveries
           SET status = ?, last_status_code = ?, last_error = ?,
               updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (status, status_code, error, delivery_id),
    )
    db.commit()


def _deliver_to_device(
    db,
    row,
    *,
    category: str,
    event_key: str,
    message: dict,
    private_key: str,
) -> bool:
    endpoint_hash = _endpoint_hash(row["endpoint"])
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        """INSERT OR IGNORE INTO push_notification_deliveries
           (user_id, notification_type, event_key, endpoint_hash, status)
           VALUES (?, ?, ?, ?, 'sending')""",
        (row["user_id"], category, event_key, endpoint_hash),
    )
    delivery = db.execute(
        """SELECT id, status, attempts, last_status_code
           FROM push_notification_deliveries
           WHERE notification_type = ? AND event_key = ? AND endpoint_hash = ?""",
        (category, event_key, endpoint_hash),
    ).fetchone()
    if delivery["status"] != "sending":
        db.commit()
        return False
    if delivery["attempts"] != 0:
        stale = db.execute(
            """SELECT updated_at < datetime('now', ?)
               FROM push_notification_deliveries WHERE id = ?""",
            (f"-{STALE_DELIVERY_MINUTES} minutes", delivery["id"]),
        ).fetchone()[0]
        if stale:
            _record_failure(
                db,
                delivery["id"],
                status="uncertain",
                status_code=delivery["last_status_code"],
                error="A previous delivery attempt did not finish.",
            )
        else:
            db.commit()
        return False
    db.execute(
        """UPDATE push_notification_deliveries
           SET attempts = 1, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (delivery["id"],),
    )
    db.commit()

    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        if attempt > 1:
            db.execute(
                """UPDATE push_notification_deliveries
                   SET attempts = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (attempt, delivery["id"]),
            )
            db.commit()
        try:
            _send_web_push(
                json.loads(row["subscription_json"]), message, private_key
            )
        except PushDeliveryError as error:
            status_code = error.status_code
            if status_code in INVALID_SUBSCRIPTION_STATUS_CODES:
                _record_failure(
                    db,
                    delivery["id"],
                    status="invalid",
                    status_code=status_code,
                    error=f"Push service returned HTTP {status_code}.",
                )
                db.execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = ?",
                    (row["endpoint"],),
                )
                db.commit()
                logger.warning(
                    "Push delivery invalidated (category=%s, event=%s, user_id=%s, HTTP %s).",
                    category,
                    event_key,
                    row["user_id"],
                    status_code,
                )
                return False

            if status_code in TRANSIENT_STATUS_CODES:
                if attempt < MAX_DELIVERY_ATTEMPTS:
                    db.execute(
                        """UPDATE push_notification_deliveries
                           SET last_status_code = ?, last_error = ?,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        (
                            status_code,
                            f"Transient push service response: HTTP {status_code}.",
                            delivery["id"],
                        ),
                    )
                    db.commit()
                    time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                    continue
                _record_failure(
                    db,
                    delivery["id"],
                    status="failed",
                    status_code=status_code,
                    error=f"Push service retries exhausted at HTTP {status_code}.",
                )
            elif status_code is None:
                _record_failure(
                    db,
                    delivery["id"],
                    status="uncertain",
                    status_code=None,
                    error="Push service connection failed; delivery outcome is uncertain.",
                )
            else:
                _record_failure(
                    db,
                    delivery["id"],
                    status="failed",
                    status_code=status_code,
                    error=f"Push service returned HTTP {status_code}.",
                )
            logger.warning(
                "Push delivery failed (category=%s, event=%s, user_id=%s, HTTP %s).",
                category,
                event_key,
                row["user_id"],
                status_code or "unknown",
            )
            return False

        db.execute(
            """UPDATE push_notification_deliveries
               SET status = 'sent', last_status_code = NULL, last_error = NULL,
                   sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (delivery["id"],),
        )
        db.commit()
        return True

    return False


def _send_event(
    category: str,
    event_key: str,
    message: dict,
    recipients,
) -> int:
    recipient_rows = list(recipients)
    if not recipient_rows:
        return 0
    private_key = _load_private_key()
    db = get_db()
    sent = 0
    for row in recipient_rows:
        if _deliver_to_device(
            db,
            row,
            category=category,
            event_key=event_key,
            message=message,
            private_key=private_key,
        ):
            sent += 1
    return sent


def send_daily_game_notifications(
    app: Flask, now: datetime | None = None
) -> int:
    """Send today's featured game to opted-in subscribed devices in its UK send window."""
    now = _normalise_now(now)
    with app.app_context():
        if not _in_send_window("daily_game", now):
            return 0

        from .routes import todays_featured_quiz

        quiz = todays_featured_quiz(now)
        if (
            quiz is None
            or not quiz.total_players
            or quiz.availability(now) != "playable"
        ):
            return 0
        recipients = get_db().execute(
            """SELECT u.id AS user_id, s.endpoint, s.subscription_json
               FROM users u
               JOIN push_subscriptions s ON s.user_id = u.id
               WHERE u.daily_game_notifications = 1
               ORDER BY u.id, s.endpoint"""
        ).fetchall()
        return _send_event(
            "daily_game",
            quiz.quiz_id,
            {
                "title": DAILY_GAME_TITLE,
                "body": f"Tap to play {quiz.home_team} vs {quiz.away_team}.",
                "url": "/featured",
            },
            recipients,
        )


def send_my_team_notifications(
    app: Flask, now: datetime | None = None
) -> int:
    """Send each playable fixture for opted-in users' teams in its UK send window."""
    now = _normalise_now(now)
    with app.app_context():
        if not _in_send_window("my_team", now):
            return 0

        from .routes import todays_featured_quiz

        daily_quiz = todays_featured_quiz(now)
        daily_match = (
            _fixture_key(daily_quiz)
            if daily_quiz is not None
            and daily_quiz.total_players
            and daily_quiz.availability(now) == "playable"
            else None
        )
        quizzes_by_match = {}
        for quiz in [
            *current_app.config["QUIZZES"],
            *current_app.config.get("FEATURED_QUIZZES", []),
        ]:
            if (
                quiz.fixture_date.date() != now.date()
                or not quiz.total_players
                or quiz.availability(now) != "playable"
            ):
                continue
            match_key = _fixture_key(quiz)
            if match_key == daily_match:
                continue
            existing = quizzes_by_match.get(match_key)
            if existing is None or (quiz.is_featured and not existing.is_featured):
                quizzes_by_match[match_key] = quiz

        if not quizzes_by_match:
            return 0

        users = get_db().execute(
            """SELECT u.id AS user_id, u.supported_team, s.endpoint, s.subscription_json
               FROM users u
               JOIN push_subscriptions s ON s.user_id = u.id
               WHERE u.my_team_notifications = 1
                 AND u.supported_team != 'Neutral'
               ORDER BY u.id, s.endpoint"""
        ).fetchall()
        recipients_by_event = {}
        for quiz in quizzes_by_match.values():
            team_pair = {quiz.home_team, quiz.away_team}
            recipients_by_event[quiz.quiz_id] = (
                quiz,
                [row for row in users if row["supported_team"] in team_pair],
            )

        sent = 0
        for event_key, (quiz, recipients) in recipients_by_event.items():
            sent += _send_event(
                "my_team",
                event_key,
                {
                    "title": MY_TEAM_TITLE,
                    "body": f"{quiz.home_team} vs {quiz.away_team} is ready to play.",
                    "url": f"/quiz/{quiz.quiz_id}",
                },
                recipients,
            )
        return sent


def send_test_notification(app: Flask, email: str) -> tuple[int, int]:
    """Send a one-off test only to devices subscribed by the specified account."""
    with app.app_context():
        user = get_db().execute(
            "SELECT id FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip(),),
        ).fetchone()
        if user is None:
            raise ValueError("No account was found for that email address.")
        recipients = get_db().execute(
            """SELECT user_id, endpoint, subscription_json
               FROM push_subscriptions WHERE user_id = ?
               ORDER BY endpoint""",
            (user["id"],),
        ).fetchall()
        if not recipients:
            raise ValueError("That account has no subscribed devices.")
        private_key = _load_private_key()
        message = {
            "title": "Two Teamers test notification",
            "body": "Push notifications are working on this device.",
            "url": "/profile",
        }
        db = get_db()
        sent = 0
        failed = 0
        for row in recipients:
            try:
                _send_web_push(
                    json.loads(row["subscription_json"]), message, private_key
                )
                sent += 1
            except PushDeliveryError as error:
                failed += 1
                if error.status_code in INVALID_SUBSCRIPTION_STATUS_CODES:
                    db.execute(
                        "DELETE FROM push_subscriptions WHERE endpoint = ?",
                        (row["endpoint"],),
                    )
                logger.warning(
                    "Test push failed for user_id=%s (HTTP %s).",
                    row["user_id"],
                    error.status_code or "unknown",
                )
        db.commit()
        return sent, failed


def send_daily_notifications(app: Flask, now: datetime | None = None) -> int:
    """Backward-compatible name for the Daily Game sender."""
    return send_daily_game_notifications(app, now)
