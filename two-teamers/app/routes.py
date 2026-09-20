from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request

from .auth import login_required
from .badges import BADGE_FILES
from .data_loader import QUIZ_TIMEZONE, slugify
from .db import get_db, get_progress, progress_counts, save_progress
from .leaderboard import calculate_standings, fan_standing
from .matching import MatchResult, match_guess

bp = Blueprint("main", __name__)


def _quiz_or_404(quiz_id):
    quiz = current_app.config["QUIZZES_BY_ID"].get(quiz_id)
    if quiz is None:
        abort(404)
    return quiz


def _availability(quiz):
    return "playable" if current_app.config["BYPASS_AVAILABILITY"] else quiz.availability()


def _public_player(quiz, player, index):
    return {
        "index": index, "name": player.name,
        "home_team": quiz.home_team, "away_team": quiz.away_team,
        "home_years": player.home.years, "home_apps": player.home.apps, "home_goals": player.home.goals,
        "away_years": player.away.years, "away_apps": player.away.apps, "away_goals": player.away.goals,
    }


def _fixture_view(quiz, counts):
    solved_count, given_up = counts.get(quiz.quiz_id, (0, False))
    return {"quiz": quiz, "status": _availability(quiz), "solved_count": solved_count, "given_up": given_up}


def _active_matchweek(quizzes):
    now = datetime.now(QUIZ_TIMEZONE)
    upcoming = next((quiz for quiz in quizzes if quiz.fixture_date >= now), None)
    return upcoming.matchweek if upcoming else quizzes[-1].matchweek


@bp.route("/")
@login_required
def home():
    return render_template("home.html")


@bp.route("/teams")
@login_required
def teams():
    return render_template(
        "teams.html",
        leagues=current_app.config["LEAGUES"],
        badge_files=BADGE_FILES,
    )


@bp.route("/team/<club_slug>")
@login_required
def team_fixtures(club_slug):
    clubs = [club for league in current_app.config["LEAGUES"] for club in league.clubs]
    club = next(
        (name for name in clubs if club_slug in (slugify(name), slugify(name.replace("&", "and")))),
        None,
    )
    if club is None:
        abort(404)
    quizzes = [quiz for quiz in current_app.config["QUIZZES"] if club in (quiz.home_team, quiz.away_team)]
    counts = progress_counts(g.user["id"])
    return render_template("fixtures.html", title=club, subtitle="2026/27 fixtures", fixtures=[_fixture_view(q, counts) for q in quizzes], coming_soon=not quizzes)


@bp.route("/leagues")
@login_required
def leagues():
    return render_template("leagues.html", leagues=current_app.config["LEAGUES"])


@bp.route("/leaderboard")
@login_required
def leaderboard():
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
        get_db(), quizzes, clubs, scoped_week
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
@login_required
def league_fixtures(league_id):
    league = current_app.config["LEAGUES_BY_ID"].get(league_id)
    if league is None:
        abort(404)
    if not league.enabled:
        return render_template("fixtures.html", title=league.name, subtitle="Coming soon", fixtures=[], coming_soon=True)
    all_quizzes = [quiz for quiz in current_app.config["QUIZZES"] if quiz.league_id == league_id]
    requested_week = request.args.get("week", type=int)
    matchweek = requested_week if requested_week and 1 <= requested_week <= 38 else _active_matchweek(all_quizzes)
    quizzes = [quiz for quiz in all_quizzes if quiz.matchweek == matchweek]
    counts = progress_counts(g.user["id"])
    return render_template("fixtures.html", title=league.name, subtitle=f"Matchweek {matchweek}", fixtures=[_fixture_view(q, counts) for q in quizzes], matchweek=matchweek, coming_soon=False)


@bp.route("/quiz/<quiz_id>")
@login_required
def quiz_page(quiz_id):
    quiz = _quiz_or_404(quiz_id)
    status = _availability(quiz)
    if status != "playable":
        return render_template("locked.html", quiz=quiz, status=status)
    state = get_progress(g.user["id"], quiz_id)
    solved = set(state["solved"])
    players = [
        {"found": index in solved or state["given_up"], **(_public_player(quiz, player, index) if index in solved or state["given_up"] else {"index": index})}
        for index, player in enumerate(quiz.players)
    ]
    return render_template("quiz.html", quiz=quiz, players=players, solved_count=len(solved), completed=len(solved) == quiz.total_players, given_up=state["given_up"])


def _guard_quiz(quiz_id):
    quiz = current_app.config["QUIZZES_BY_ID"].get(quiz_id)
    if quiz is None:
        return None, (jsonify({"status": "error", "message": "Unknown game."}), 404)
    status = _availability(quiz)
    if status != "playable":
        message = "This game has expired." if status == "expired" else "This game unlocks at 4am on match day."
        return None, (jsonify({"status": status, "message": message}), 403)
    return quiz, None


def _start_score(state, quiz):
    if not state["score_started"]:
        state["score_started"] = True
        state["score_total"] = quiz.total_players


def _guess_response(quiz, exact_only=False):
    state = get_progress(g.user["id"], quiz.quiz_id)
    solved = set(state["solved"])
    guess = str((request.get_json(silent=True) or {}).get("guess", "")).strip()
    outcome = match_guess(guess, quiz.players, solved)
    if exact_only and outcome.result != MatchResult.EXACT:
        return jsonify({"status": "not_exact"})
    _start_score(state, quiz)
    if outcome.result in (MatchResult.EXACT, MatchResult.CORRECT):
        solved.add(outcome.player_index)
        state["solved"] = sorted(solved)
        if not state["score_frozen"]:
            state["score_correct"] += 1
            if state["score_correct"] >= state["score_total"]:
                state["score_frozen"] = True
        save_progress(g.user["id"], quiz.quiz_id, state)
        player = quiz.players[outcome.player_index]
        return jsonify({"status": "correct", "message": "Correct!", "player": _public_player(quiz, player, outcome.player_index), "solved_count": len(solved), "total": quiz.total_players, "completed": len(solved) == quiz.total_players})
    if outcome.result == MatchResult.NEAR:
        save_progress(g.user["id"], quiz.quiz_id, state)
        return jsonify({"status": "near", "message": "Close but not quite.", "score": outcome.score})
    save_progress(g.user["id"], quiz.quiz_id, state)
    return jsonify({"status": "wrong", "message": "Not a match. Keep trying."})


@bp.post("/quiz/<quiz_id>/guess")
@login_required
def submit_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _guess_response(quiz)


@bp.post("/quiz/<quiz_id>/exact")
@login_required
def submit_exact_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _guess_response(quiz, exact_only=True)


@bp.post("/quiz/<quiz_id>/clue")
@login_required
def request_clue(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    data = request.get_json(silent=True) or {}
    types = [
        value
        for value in data.get("types", [])
        if value in ("apps", "goals", "years", "initials")
    ]
    if not types:
        return jsonify({"status": "error", "message": "Choose at least one clue."}), 400
    state = get_progress(g.user["id"], quiz_id)
    _start_score(state, quiz)
    state["score_frozen"] = True
    save_progress(g.user["id"], quiz_id, state)
    solved = set(state["solved"])
    target = data.get("index")
    indices = range(len(quiz.players)) if target in (None, "all") else [int(target)]
    clues = []
    for index in indices:
        if index in solved or not 0 <= index < len(quiz.players):
            continue
        player = quiz.players[index]
        clues.append({"index": index, **{kind: player.clue_value(kind, quiz.home_team, quiz.away_team) for kind in types}})
    return jsonify({"status": "ok", "clues": clues})


@bp.post("/quiz/<quiz_id>/giveup")
@login_required
def give_up(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    if not (request.get_json(silent=True) or {}).get("confirm"):
        return jsonify({"status": "error"}), 400
    state = get_progress(g.user["id"], quiz_id)
    _start_score(state, quiz)
    state["score_frozen"] = True
    state["given_up"] = True
    save_progress(g.user["id"], quiz_id, state)
    return jsonify({"status": "given_up", "players": [_public_player(quiz, player, index) for index, player in enumerate(quiz.players)], "total": quiz.total_players})


@bp.post("/quiz/<quiz_id>/reset")
@login_required
def reset_quiz(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    state = get_progress(g.user["id"], quiz_id)
    if state["score_started"]:
        state["score_frozen"] = True
    state["solved"] = []
    state["given_up"] = False
    save_progress(g.user["id"], quiz_id, state)
    return jsonify({"status": "reset"})
