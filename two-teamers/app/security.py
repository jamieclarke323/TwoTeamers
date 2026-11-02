from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from flask import Flask, current_app, jsonify, request, session

from .db import get_db


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def init_security(app: Flask) -> None:
    if not app.testing and not app.config["DEVELOPMENT"]:
        key = app.secret_key
        if not isinstance(key, str) or len(key) < 32 or key == "dev-secret-key-change-me":
            raise RuntimeError("Production requires a unique random SECRET_KEY of at least 32 characters.")
        if not app.config["SESSION_COOKIE_SECURE"]:
            raise RuntimeError("Production requires SESSION_COOKIE_SECURE=1.")
    elif not app.secret_key:
        app.secret_key = secrets.token_hex(32)

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_writes():
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        origin = request.headers.get("Origin")
        if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
            origin and origin != request.host_url.rstrip("/")
        ):
            return jsonify(message="Cross-site request rejected.", error="Cross-site request rejected."), 403
        if not app.config["CSRF_ENABLED"]:
            return None
        # These endpoints require an expiring, owner-bound signed download token.
        if request.endpoint in {"offline.sync_quiz", "offline.refresh_quiz"} and request.is_json:
            return None
        if request.endpoint and request.endpoint.startswith("auth.") and request.path.startswith("/push/"):
            return None
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        expected = session.get("csrf_token")
        if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
            message = "Refresh this page and try again. Your security token is missing or expired."
            return jsonify(message=message, error=message), 403
        return None

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if response.mimetype == "text/html" or request.path.startswith("/push/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def check_auth_rate_limit(kind: str, email: str):
    if not current_app.config["AUTH_RATE_LIMIT_ENABLED"]:
        return None
    now = int(time.time())
    secret = str(current_app.secret_key).encode()
    identifiers = [(f"{kind}:ip:{request.remote_addr}", 60 if kind == "login" else 10)]
    if kind == "login":
        identifiers.append((f"login:email:{email}", 20))
    window = 900 if kind == "login" else 3600
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("DELETE FROM auth_attempts WHERE attempted_at < ?", (now - 3600,))
        keys = [
            (hmac.new(secret, identifier.encode(), hashlib.sha256).hexdigest(), limit)
            for identifier, limit in identifiers
        ]
        limited = any(
            db.execute(
                "SELECT COUNT(*) FROM auth_attempts WHERE bucket = ? AND attempted_at > ?",
                (key, now - window),
            ).fetchone()[0] >= limit
            for key, limit in keys
        )
        if not limited:
            db.executemany(
                "INSERT INTO auth_attempts (bucket, attempted_at) VALUES (?, ?)",
                [(key, now) for key, _ in keys],
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    if limited:
        response = jsonify(message="Too many attempts. Please try again later.")
        response.status_code = 429
        response.headers["Retry-After"] = str(window)
        return response
    return None
