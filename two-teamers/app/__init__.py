from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .data_loader import FEATURED_WORKBOOK, load_game_data
from .db import close_db, init_db

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR.parent


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key-change-me"),
        DATABASE=os.environ.get("DATABASE_PATH", str(PROJECT_DIR / "instance" / "two-teamers.sqlite")),
        DATA_DIR=os.environ.get("FIXTURES_DIR", str(DATA_DIR)),
        XLSX_PATH=os.environ.get("PLAYERS_XLSX_PATH", str(DATA_DIR / "2627DataSource.xlsx")),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        REMEMBER_COOKIE_DURATION=timedelta(days=30),
        SESSION_REFRESH_EACH_REQUEST=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        BYPASS_AVAILABILITY=os.environ.get("BYPASS_AVAILABILITY", "0") == "1",
        REWARDED_ADS_ENABLED=os.environ.get("REWARDED_ADS_ENABLED", "0") == "1",
        # Scores are always recorded; this only controls whether users can see the leaderboard.
        LEADERBOARD_ENABLED=os.environ.get("LEADERBOARD_ENABLED", "0") == "1",
        # Blank client ID with ads enabled uses a simulated ad for local testing.
        ADSENSE_CLIENT_ID=os.environ.get("ADSENSE_CLIENT_ID", ""),
        ADSENSE_TEST_MODE=os.environ.get("ADSENSE_TEST_MODE", "1") == "1",
    )
    if test_config:
        app.config.update(test_config)
    app.config.setdefault(
        "FEATURED_XLSX_PATH",
        os.environ.get("FEATURED_XLSX_PATH", str(Path(app.config["DATA_DIR"]) / FEATURED_WORKBOOK)),
    )

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    init_db(app)
    leagues, quizzes, featured = load_game_data(app.config["DATA_DIR"], app.config["FEATURED_XLSX_PATH"])
    app.config["LEAGUES"] = leagues
    app.config["LEAGUES_BY_ID"] = {league.league_id: league for league in leagues}
    app.config["QUIZZES"] = quizzes
    app.config["FEATURED_QUIZZES"] = featured
    app.config["QUIZZES_BY_ID"] = {quiz.quiz_id: quiz for quiz in [*quizzes, *featured]}

    from .auth import bp as auth_bp
    from .routes import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.teardown_appcontext(close_db)
    return app
