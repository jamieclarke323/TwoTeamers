from __future__ import annotations

import json
import re
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, transfer_guest_progress

bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    g.user = None if user_id is None else get_db().execute(
        "SELECT id, email, supported_team FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def _team_choices() -> list[str]:
    clubs = {
        club
        for league in current_app.config["LEAGUES"]
        for club in league.clubs
    }
    return ["Neutral", *sorted(clubs)]


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped_view


def _safe_next(value: str | None) -> str | None:
    if not value:
        return None
    host_url = urlparse(request.host_url)
    target = urlparse(urljoin(request.host_url, value))
    if target.scheme == host_url.scheme and target.netloc == host_url.netloc:
        return target.path
    return None


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if g.user is not None:
        return redirect(url_for("main.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        supported_team = request.form.get("supported_team", "")
        error = None
        if not EMAIL_PATTERN.match(email):
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif supported_team not in _team_choices():
            error = "Choose the team you support, or select Neutral."
        elif get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            error = "An account already exists for that email."
        if error:
            flash(error, "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO users (email, password_hash, supported_team) VALUES (?, ?, ?)",
                (email, generate_password_hash(password), supported_team),
            )
            db.commit()
            user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            visitor_id = session.get("visitor_id")
            if visitor_id:
                transfer_guest_progress(visitor_id, user["id"])
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("main.home"))
    return render_template("auth.html", mode="signup", team_choices=_team_choices())


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("main.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email or password is incorrect.", "error")
        else:
            visitor_id = session.get("visitor_id")
            if visitor_id:
                transfer_guest_progress(visitor_id, user["id"])
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            get_db().execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            get_db().commit()
            return redirect(_safe_next(request.args.get("next")) or url_for("main.home"))
    return render_template("auth.html", mode="login")


@bp.route("/profile", methods=("GET", "POST"))
@login_required
def profile():
    team_choices = _team_choices()
    if request.method == "POST":
        supported_team = request.form.get("supported_team", "")
        if supported_team not in team_choices:
            flash("Choose a valid team, or select Neutral.", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE users SET supported_team = ? WHERE id = ?",
                (supported_team, g.user["id"]),
            )
            db.commit()
            flash("Your team has been updated.", "success")
            return redirect(url_for("auth.profile"))
    subscription_count = get_db().execute(
        "SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (g.user["id"],)
    ).fetchone()[0]
    return render_template(
        "profile.html",
        team_choices=team_choices,
        push_notifications_available=bool(current_app.config["PUSH_VAPID_PUBLIC_KEY"]),
        push_public_key=current_app.config["PUSH_VAPID_PUBLIC_KEY"],
        has_push_subscriptions=subscription_count > 0,
    )


def _valid_push_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    allowed_suffixes = (
        "fcm.googleapis.com",
        "push.services.mozilla.com",
        "push.apple.com",
        "notify.windows.com",
    )
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes)
    )


@bp.post("/push/subscribe")
@login_required
def save_push_subscription():
    if not current_app.config["PUSH_VAPID_PUBLIC_KEY"]:
        return jsonify({"error": "Push notifications are not configured."}), 503
    subscription = request.get_json(silent=True)
    if not isinstance(subscription, dict):
        return jsonify({"error": "A valid push subscription is required."}), 400
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys")
    if (
        not isinstance(endpoint, str)
        or not _valid_push_endpoint(endpoint)
        or not isinstance(keys, dict)
        or not isinstance(keys.get("p256dh"), str)
        or not keys["p256dh"]
        or not isinstance(keys.get("auth"), str)
        or not keys["auth"]
    ):
        return jsonify({"error": "A valid push subscription is required."}), 400
    get_db().execute(
        """INSERT INTO push_subscriptions (endpoint, user_id, subscription_json)
           VALUES (?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET
             user_id = excluded.user_id,
             subscription_json = excluded.subscription_json""",
        (endpoint, g.user["id"], json.dumps(subscription)),
    )
    get_db().commit()
    return jsonify({"status": "subscribed"})


@bp.post("/push/unsubscribe")
@login_required
def remove_push_subscription():
    subscription = request.get_json(silent=True)
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else None
    if not isinstance(endpoint, str) or not _valid_push_endpoint(endpoint):
        return jsonify({"error": "A valid push subscription is required."}), 400
    get_db().execute(
        "DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?",
        (endpoint, g.user["id"]),
    )
    get_db().commit()
    return jsonify({"status": "unsubscribed"})


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
