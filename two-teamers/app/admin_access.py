import hashlib
import hmac
import time

from flask import current_app, render_template, request, session
from werkzeug.security import check_password_hash

from .db import get_db


def require_admin_password():
    password_hash = current_app.config["ADMIN_PASSWORD_HASH"]
    if not password_hash:
        current_app.logger.error("Admin access is unavailable: ADMIN_PASSWORD_HASH is not configured.")
        return render_template("admin_login.html", error="Admin access is not configured."), 503

    now = int(time.time())
    fingerprint = hashlib.sha256(password_hash.encode()).hexdigest()
    access = session.get("admin_access", {})
    if access.get("key") == fingerprint and access.get("expires", 0) > now:
        return None

    bucket = hmac.new(
        str(current_app.secret_key).encode(),
        f"admin:{request.remote_addr}".encode(),
        hashlib.sha256,
    ).hexdigest()
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT failures, locked_until FROM admin_access_attempts WHERE bucket = ?",
            (bucket,),
        ).fetchone()
        failures = row["failures"] if row else 0
        locked_until = row["locked_until"] if row else 0
        if locked_until > now:
            db.commit()
            return _locked_response(locked_until - now)
        if locked_until:
            failures = 0
            db.execute("DELETE FROM admin_access_attempts WHERE bucket = ?", (bucket,))
        error = None
        status = 200
        if request.method == "POST":
            if check_password_hash(password_hash, request.form.get("password", "")):
                db.execute("DELETE FROM admin_access_attempts WHERE bucket = ?", (bucket,))
                db.commit()
                session["admin_access"] = {"key": fingerprint, "expires": now + 3600}
                return None
            failures += 1
            locked_until = now + 600 if failures >= 5 else 0
            db.execute(
                """INSERT INTO admin_access_attempts (bucket, failures, locked_until)
                   VALUES (?, ?, ?)
                   ON CONFLICT(bucket) DO UPDATE SET
                   failures = excluded.failures, locked_until = excluded.locked_until""",
                (bucket, failures, locked_until),
            )
            if locked_until:
                db.commit()
                return _locked_response(600)
            error = f"Incorrect password. {5 - failures} attempts remaining."
            status = 401
        db.commit()
    except Exception:
        db.rollback()
        raise
    return render_template("admin_login.html", error=error), status


def _locked_response(seconds):
    return (
        render_template("admin_login.html", error="Too many incorrect attempts. Please try again in 10 minutes."),
        429,
        {"Retry-After": str(seconds)},
    )
