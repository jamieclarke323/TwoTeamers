from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from .auth import login_required
from .badges import BADGE_FILES
from .data_loader import FEATURED_UNLOCK, QUIZ_TIMEZONE, _shared_players, slugify
from .db import get_db, get_progress, progress_counts, save_progress
from .leaderboard import calculate_standings, fan_standing
from .gameplay import (
    answer_data as _answer_data, apply_action, game_completed,
    public_player as _public_player, revealed_indices, share_result_text as _share_result_text,
)

bp = Blueprint("main", __name__)


@bp.get("/service-worker.js")
def service_worker():
    response = send_from_directory(current_app.static_folder, "service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


def todays_featured_quiz(now: datetime | None = None):
    now = now or datetime.now(QUIZ_TIMEZONE)
    # Each featured game opens at 00:01, so 00:00-00:00:59 still belongs to the previous day.
    featured_day = (now - timedelta(hours=FEATURED_UNLOCK.hour, minutes=FEATURED_UNLOCK.minute)).date()
    return next(
        (quiz for quiz in current_app.config.get("FEATURED_QUIZZES", []) if quiz.fixture_date.date() == featured_day),
        None,
    )


@bp.app_context_processor
def inject_featured_fixture():
    quiz = todays_featured_quiz()
    if quiz is None:
        return {"featured_fixture": None}
    return {
        "featured_fixture": {
            "quiz": quiz,
            "home_kit": BADGE_FILES.get(quiz.home_team),
            "away_kit": BADGE_FILES.get(quiz.away_team),
        }
    }


def _quiz_or_404(quiz_id):
    quiz = current_app.config["QUIZZES_BY_ID"].get(quiz_id)
    if quiz is None:
        abort(404)
    return quiz


def _availability(quiz):
    return "playable" if current_app.config["BYPASS_AVAILABILITY"] else quiz.availability()


def _progress_identity() -> int | str:
    if g.user is not None:
        return g.user["id"]
    visitor_id = session.get("visitor_id")
    if visitor_id is None:
        visitor_id = str(uuid4())
        session["visitor_id"] = visitor_id
    session.permanent = True
    return visitor_id


def _fixture_view(quiz, counts):
    solved_count, given_up = counts.get(quiz.quiz_id, (0, False))
    status = "no_answers" if quiz.total_players == 0 else _availability(quiz)
    return {"quiz": quiz, "status": status, "solved_count": solved_count, "given_up": given_up}


def _active_matchweek(quizzes):
    now = datetime.now(QUIZ_TIMEZONE)
    upcoming = next((quiz for quiz in quizzes if quiz.fixture_date >= now), None)
    return upcoming.matchweek if upcoming else quizzes[-1].matchweek


@bp.route("/")
def home():
    team_quiz = None
    team_status = None
    if g.user is not None:
        fixtures = sorted(
            (quiz for quiz in current_app.config["QUIZZES"]
             if g.user["supported_team"] in (quiz.home_team, quiz.away_team)),
            key=lambda quiz: quiz.fixture_date,
        )
        team_quiz = next(
            (quiz for quiz in fixtures if quiz.total_players and _availability(quiz) == "playable"), None,
        )
        if team_quiz is None:
            team_quiz = next((quiz for quiz in fixtures if _availability(quiz) == "upcoming"), None)
        if team_quiz is not None:
            team_status = _availability(team_quiz)
    return render_template(
        "home.html", daily_quiz=todays_featured_quiz(), team_quiz=team_quiz,
        team_status=team_status, badge_files=BADGE_FILES, hide_featured_banner=True,
    )


@bp.route("/teams")
def teams():
    return render_template(
        "teams.html",
        leagues=current_app.config["LEAGUES"],
        badge_files=BADGE_FILES,
    )


@bp.route("/team/<club_slug>")
def team_fixtures(club_slug):
    clubs = [club for league in current_app.config["LEAGUES"] for club in league.clubs]
    club = next(
        (name for name in clubs if club_slug in (slugify(name), slugify(name.replace("&", "and")))),
        None,
    )
    if club is None:
        abort(404)
    quizzes = [quiz for quiz in current_app.config["QUIZZES"] if club in (quiz.home_team, quiz.away_team)]
    counts = progress_counts(_progress_identity())
    fixtures = [_fixture_view(quiz, counts) for quiz in quizzes]
    auto_scroll_quiz_id = next(
        (item["quiz"].quiz_id for item in fixtures if item["status"] == "playable"),
        None,
    )
    return render_template(
        "fixtures.html",
        title=club,
        subtitle="2026/27 fixtures",
        fixtures=fixtures,
        coming_soon=not quizzes,
        auto_scroll_quiz_id=auto_scroll_quiz_id,
    )


@bp.route("/leagues")
def leagues():
    return render_template("leagues.html", leagues=current_app.config["LEAGUES"])


@bp.route("/leaderboard")
def leaderboard():
    if not current_app.config.get("LEADERBOARD_ENABLED", False):
        abort(404)
    return _leaderboard_page()


@login_required
def _leaderboard_page():
    mode = request.args.get("mode", "season")
    if mode not in ("season", "matchweek"):
        mode = "season"
    quizzes = current_app.config["QUIZZES"]
    maximum_matchweek = max(quiz.matchweek for quiz in quizzes)
    requested_week = request.args.get("week", type=int)
    active_week = _active_matchweek(quizzes)
    matchweek = min(max(requested_week or active_week, 1), maximum_matchweek)
    scoped_week = matchweek if mode == "matchweek" else None
    clubs = sorted(
        {
            club
            for league in current_app.config["LEAGUES"]
            for club in league.clubs
        }
    )
    standings, user_averages, users_by_team, scores_by_user = calculate_standings(
        get_db(), [*quizzes, *current_app.config.get("FEATURED_QUIZZES", [])], clubs, scoped_week
    )
    personal = fan_standing(
        g.user["id"],
        g.user["supported_team"],
        user_averages,
        users_by_team,
        scores_by_user,
    )
    return render_template(
        "leaderboard.html",
        standings=standings,
        personal=personal,
        supported_team=g.user["supported_team"],
        badge_files=BADGE_FILES,
        mode=mode,
        matchweek=matchweek,
        maximum_matchweek=maximum_matchweek,
    )


@bp.route("/league/<league_id>")
def league_fixtures(league_id):
    league = current_app.config["LEAGUES_BY_ID"].get(league_id)
    if league is None:
        abort(404)
    if not league.enabled:
        return render_template("fixtures.html", title=league.name, subtitle="Coming soon", fixtures=[], coming_soon=True)
    all_quizzes = [quiz for quiz in current_app.config["QUIZZES"] if quiz.league_id == league_id]
    maximum_matchweek = max(quiz.matchweek for quiz in all_quizzes)
    requested_week = request.args.get("week", type=int)
    matchweek = (
        requested_week
        if requested_week and 1 <= requested_week <= maximum_matchweek
        else _active_matchweek(all_quizzes)
    )
    quizzes = [quiz for quiz in all_quizzes if quiz.matchweek == matchweek]
    counts = progress_counts(_progress_identity())
    return render_template(
        "fixtures.html",
        title=league.name,
        subtitle=f"Matchweek {matchweek}",
        fixtures=[_fixture_view(q, counts) for q in quizzes],
        matchweek=matchweek,
        maximum_matchweek=maximum_matchweek,
        league_id=league_id,
        coming_soon=False,
    )


@bp.route("/admin", methods=["GET"])
@bp.route("/admin/matchup", methods=["GET"])
def admin_matchup():
    all_rosters = current_app.config.get("ALL_ROSTERS", {})
    clubs = current_app.config.get("ALL_CLUBS", sorted(all_rosters.keys()))
    team1 = request.args.get("team1", "").strip()
    team2 = request.args.get("team2", "").strip()
    players = []
    searched = bool(team1 and team2)
    same_team = False
    if searched:
        if team1 == team2:
            same_team = True
        else:
            players = _shared_players(all_rosters, team1, team2)
    return render_template(
        "admin_matchup.html",
        clubs=clubs,
        team1=team1,
        team2=team2,
        players=players,
        searched=searched,
        same_team=same_team,
        hide_featured_banner=True,
    )


SUPPORT_EMAIL = "twoteamerssupport@gmail.com"
REPORT_TYPES = (
    "App functionality",
    "Stats error",
    "Valid answer not listed/Invalid answer listed",
    "Other",
)


@bp.route("/report")
def report_bug():
    return render_template("report.html", report_types=REPORT_TYPES)


@bp.route("/report/send")
def send_report():
    report_type = request.args.get("type", "")
    if report_type not in REPORT_TYPES:
        flash("Please choose a type of error.", "error")
        return redirect(url_for("main.report_bug"))
    return redirect(f"mailto:{SUPPORT_EMAIL}?subject={quote(report_type)}")


@bp.route("/featured")
def featured_game():
    quiz = todays_featured_quiz()
    if quiz is None:
        flash("There's no featured fixture today. Check back tomorrow!", "info")
        return redirect(url_for("main.home"))
    return _render_quiz(quiz)


@bp.route("/quiz/<quiz_id>")
def quiz_page(quiz_id):
    quiz = _quiz_or_404(quiz_id)
    if quiz.is_featured and quiz is todays_featured_quiz():
        return redirect(url_for("main.featured_game"))
    return _render_quiz(quiz)


def _render_quiz(quiz, is_home_game: bool = False, offline_package=None):
    if quiz.total_players == 0:
        return render_template("locked.html", quiz=quiz, status="no_answers", hide_featured_banner=True)
    status = _availability(quiz)
    if status != "playable":
        return render_template("locked.html", quiz=quiz, status=status, hide_featured_banner=True)
    state = offline_package["state"] if offline_package is not None else get_progress(_progress_identity(), quiz.quiz_id)
    solved = set(state["solved"])
    revealed = revealed_indices(state)
    visible = solved | revealed
    saved_clues = _answer_data(state)["clues"]
    clue_labels = {"years": "Years", "initials": "Initials", "nationality": "Nationality"}
    players = [
        {"found": index in visible or state["given_up"],
         "revealed": index in revealed or (state["given_up"] and index not in solved),
         "clues": [(clue_labels[kind], player.clue_value(kind, quiz.home_team, quiz.away_team))
                   for kind in saved_clues.get(str(index), [])
                   if kind in clue_labels and (kind != "nationality" or player.has_nationality)],
         **(_public_player(quiz, player, index) if index in visible or state["given_up"] else {"index": index})}
        for index, player in enumerate(quiz.players)
    ]
    completed = game_completed(quiz, state)
    ads_enabled = _rewarded_ads_enabled()
    return render_template(
        "quiz.html",
        quiz=quiz,
        players=players,
        solved_count=len(solved),
        completed=completed,
        given_up=state["given_up"],
        share_text=_share_result_text(quiz, state) if completed or state["given_up"] else "",
        ads_enabled=ads_enabled,
        nationality_player_indices=[
            index for index, player in enumerate(quiz.players) if player.has_nationality
        ],
        clues_locked=ads_enabled and not _answer_data(state).get("clue_unlocked", False),
        adsense_client_id=current_app.config["ADSENSE_CLIENT_ID"],
        adsense_test_mode=current_app.config["ADSENSE_TEST_MODE"],
        hide_featured_banner=True,
        is_home_game=is_home_game,
        offline_package=offline_package,
        offline_mode=offline_package is not None,
    )


def _rewarded_ads_enabled():
    return current_app.config.get("REWARDED_ADS_ENABLED", False)


def _guard_quiz(quiz_id):
    quiz = current_app.config["QUIZZES_BY_ID"].get(quiz_id)
    if quiz is None:
        return None, (jsonify({"status": "error", "message": "Unknown game."}), 404)
    if quiz.total_players == 0:
        return None, (jsonify({"status": "no_answers", "message": "No shared players are listed for this fixture."}), 409)
    status = _availability(quiz)
    if status != "playable":
        message = "This game has expired." if status == "expired" else "This game unlocks at 4am on match day."
        return None, (jsonify({"status": status, "message": message}), 403)
    return quiz, None


def _action_response(quiz, action):
    identity = _progress_identity()
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        state = get_progress(identity, quiz.quiz_id)
        result, status = apply_action(
            quiz, state, action, request.get_json(silent=True) or {}, _rewarded_ads_enabled()
        )
        if status == 200 and result["status"] != "not_exact":
            save_progress(identity, quiz.quiz_id, state, commit=False)
    return jsonify(result), status


@bp.post("/quiz/<quiz_id>/guess")
def submit_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "guess")


@bp.post("/quiz/<quiz_id>/exact")
def submit_exact_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "exact")


@bp.post("/quiz/<quiz_id>/clue")
def request_clue(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "clue")


@bp.post("/quiz/<quiz_id>/clue-unlock")
def unlock_clues(quiz_id):
    # AdSense rewarded ads only report completion in the browser, so this trusts the client.
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    if not _rewarded_ads_enabled():
        return jsonify({"status": "unlocked"})
    identity = _progress_identity()
    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        state = get_progress(identity, quiz.quiz_id)
        _answer_data(state)["clue_unlocked"] = True
        save_progress(identity, quiz.quiz_id, state, commit=False)
    return jsonify({"status": "unlocked"})


@bp.post("/quiz/<quiz_id>/giveup")
def give_up(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "giveup")


@bp.post("/quiz/<quiz_id>/giveup-answer")
def give_up_answer(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "giveup-answer")


@bp.post("/quiz/<quiz_id>/reset")
def reset_quiz(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _action_response(quiz, "reset")
