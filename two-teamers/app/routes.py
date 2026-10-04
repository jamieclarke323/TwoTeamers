from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from flask import Blueprint, abort, current_app, g, jsonify, render_template, request, session

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


def _progress_identity() -> int | str:
    if g.user is not None:
        return g.user["id"]
    visitor_id = session.get("visitor_id")
    if visitor_id is None:
        visitor_id = str(uuid4())
        session["visitor_id"] = visitor_id
    session.permanent = True
    return visitor_id


def _public_player(quiz, player, index):
    return {
        "index": index, "name": player.name,
        "home_team": quiz.home_team, "away_team": quiz.away_team,
        "home_years": player.home.years, "home_apps": player.home.apps, "home_goals": player.home.goals,
        "away_years": player.away.years, "away_apps": player.away.apps, "away_goals": player.away.goals,
    }


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
    return render_template("home.html")


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
    return render_template("fixtures.html", title=club, subtitle="2026/27 fixtures", fixtures=[_fixture_view(q, counts) for q in quizzes], coming_soon=not quizzes)


@bp.route("/leagues")
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


@bp.route("/quiz/<quiz_id>")
def quiz_page(quiz_id):
    quiz = _quiz_or_404(quiz_id)
    if quiz.total_players == 0:
        return render_template("locked.html", quiz=quiz, status="no_answers")
    status = _availability(quiz)
    if status != "playable":
        return render_template("locked.html", quiz=quiz, status=status)
    state = get_progress(_progress_identity(), quiz_id)
    solved = set(state["solved"])
    players = [
        {"found": index in solved or state["given_up"], **(_public_player(quiz, player, index) if index in solved or state["given_up"] else {"index": index})}
        for index, player in enumerate(quiz.players)
    ]
    completed = len(solved) == quiz.total_players
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
        clues_locked=ads_enabled and not _answer_data(state).get("clue_unlocked", False),
        adsense_client_id=current_app.config["ADSENSE_CLIENT_ID"],
        adsense_test_mode=current_app.config["ADSENSE_TEST_MODE"],
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


def _start_score(state, quiz):
    if not state["score_started"]:
        state["score_started"] = True
        state["score_total"] = quiz.total_players


def _answer_data(state):
    data = state.setdefault("answer_data", {})
    data.setdefault("clues", {})
    data.setdefault("solve_order", [])
    return data


def _share_result_text(quiz, state):
    solved = set(state["solved"])
    answer_data = _answer_data(state)
    clue_counts = answer_data["clues"]
    symbols = []
    for index in range(quiz.total_players):
        if index not in solved:
            symbols.append("❌")
            continue
        count = len(clue_counts.get(str(index), []))
        symbols.append("🟢" if count == 0 else "🟡" if count == 1 else "🟠")

    return "\n".join(
        (
            f"TWO TEAMERS {len(solved)}/{quiz.total_players}",
            f"{quiz.home_team} vs {quiz.away_team}",
            " ".join(symbols),
            "www.placeholderlink.com",
        )
    )


def _guess_response(quiz, exact_only=False):
    identity = _progress_identity()
    state = get_progress(identity, quiz.quiz_id)
    solved = set(state["solved"])
    guess = str((request.get_json(silent=True) or {}).get("guess", "")).strip()
    outcome = match_guess(guess, quiz.players, solved)
    if exact_only and outcome.result != MatchResult.EXACT:
        return jsonify({"status": "not_exact"})
    _start_score(state, quiz)
    if outcome.result in (MatchResult.EXACT, MatchResult.CORRECT):
        answer_index = outcome.player_index
        solved.add(answer_index)
        state["solved"] = sorted(solved)
        answer_data = _answer_data(state)
        answer_data["solve_order"].append(
            {
                "index": answer_index,
                "clue_count": len(answer_data["clues"].get(str(answer_index), [])),
            }
        )
        if not state["score_frozen"]:
            state["score_correct"] += 1
            if state["score_correct"] >= state["score_total"]:
                state["score_frozen"] = True
        save_progress(identity, quiz.quiz_id, state)
        player = quiz.players[outcome.player_index]
        completed = len(solved) == quiz.total_players
        response = {
            "status": "correct",
            "message": "Correct!",
            "player": _public_player(quiz, player, answer_index),
            "solved_count": len(solved),
            "total": quiz.total_players,
            "completed": completed,
        }
        if completed:
            response["share_text"] = _share_result_text(quiz, state)
        return jsonify(response)
    if outcome.result == MatchResult.NEAR:
        save_progress(identity, quiz.quiz_id, state)
        return jsonify({"status": "near", "message": "Close but not quite.", "score": outcome.score})
    save_progress(identity, quiz.quiz_id, state)
    return jsonify({"status": "wrong", "message": "Not a match. Keep trying."})


@bp.post("/quiz/<quiz_id>/guess")
def submit_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _guess_response(quiz)


@bp.post("/quiz/<quiz_id>/exact")
def submit_exact_guess(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    return error or _guess_response(quiz, exact_only=True)


@bp.post("/quiz/<quiz_id>/clue")
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
    identity = _progress_identity()
    state = get_progress(identity, quiz_id)
    answer_data = _answer_data(state)
    if _rewarded_ads_enabled():
        if not answer_data.get("clue_unlocked"):
            return jsonify({"status": "ad_required", "message": "Watch an ad to unlock clues!"}), 403
        # Each watched ad pays for one clue reveal.
        answer_data["clue_unlocked"] = False
    _start_score(state, quiz)
    state["score_frozen"] = True
    solved = set(state["solved"])
    target = data.get("index")
    indices = range(len(quiz.players)) if target in (None, "all") else [int(target)]
    clues = []
    for index in indices:
        if index in solved or not 0 <= index < len(quiz.players):
            continue
        player_clues = answer_data["clues"].setdefault(str(index), [])
        for clue_type in types:
            if clue_type not in player_clues:
                player_clues.append(clue_type)
        player = quiz.players[index]
        clues.append({"index": index, **{kind: player.clue_value(kind, quiz.home_team, quiz.away_team) for kind in types}})
    save_progress(identity, quiz_id, state)
    return jsonify({"status": "ok", "clues": clues})


@bp.post("/quiz/<quiz_id>/clue-unlock")
def unlock_clues(quiz_id):
    # AdSense rewarded ads only report completion in the browser, so this trusts the client.
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    if not _rewarded_ads_enabled():
        return jsonify({"status": "unlocked"})
    identity = _progress_identity()
    state = get_progress(identity, quiz.quiz_id)
    _answer_data(state)["clue_unlocked"] = True
    save_progress(identity, quiz.quiz_id, state)
    return jsonify({"status": "unlocked"})


@bp.post("/quiz/<quiz_id>/giveup")
def give_up(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    if not (request.get_json(silent=True) or {}).get("confirm"):
        return jsonify({"status": "error"}), 400
    identity = _progress_identity()
    state = get_progress(identity, quiz_id)
    _start_score(state, quiz)
    state["score_frozen"] = True
    state["given_up"] = True
    save_progress(identity, quiz_id, state)
    return jsonify({
        "status": "given_up",
        "players": [_public_player(quiz, player, index) for index, player in enumerate(quiz.players)],
        "total": quiz.total_players,
        "solved_count": len(state["solved"]),
        "share_text": _share_result_text(quiz, state),
    })


@bp.post("/quiz/<quiz_id>/reset")
def reset_quiz(quiz_id):
    quiz, error = _guard_quiz(quiz_id)
    if error:
        return error
    identity = _progress_identity()
    state = get_progress(identity, quiz_id)
    if state["score_started"]:
        state["score_frozen"] = True
    state["solved"] = []
    state["given_up"] = False
    state["answer_data"] = {"clues": {}, "solve_order": []}
    save_progress(identity, quiz_id, state)
    return jsonify({"status": "reset"})
