from .matching import MatchResult, match_guess


def public_player(quiz, player, index):
    return {
        "index": index, "name": player.name,
        "home_team": quiz.home_team, "away_team": quiz.away_team,
        "home_years": player.home.years, "home_apps": player.home.apps, "home_goals": player.home.goals,
        "away_years": player.away.years, "away_apps": player.away.apps, "away_goals": player.away.goals,
    }


def start_score(state, quiz):
    if not state["score_started"]:
        state["score_started"] = True
        state["score_total"] = quiz.total_players


def answer_data(state):
    data = state.setdefault("answer_data", {})
    data.setdefault("clues", {})
    data.setdefault("solve_order", [])
    return data


def revealed_indices(state):
    return set(state.get("answer_data", {}).get("revealed", []))


def game_completed(quiz, state):
    return len(set(state["solved"]) | revealed_indices(state)) == quiz.total_players


def share_result_text(quiz, state):
    solved = set(state["solved"])
    clue_counts = answer_data(state)["clues"]
    symbols = []
    for index in range(quiz.total_players):
        if index not in solved:
            symbols.append("❌")
        else:
            count = len(clue_counts.get(str(index), []))
            symbols.append("🟢" if count == 0 else "🟡" if count == 1 else "🟠")
    return "\n".join((
        f"TWO TEAMERS {len(solved)}/{quiz.total_players}",
        f"{quiz.home_team} vs {quiz.away_team}",
        " ".join(symbols),
        "twoteamers.com",
    ))


def apply_action(quiz, state, action, data, ads_enabled=False):
    """Apply an online or replayed offline action to the same scoring rules."""
    if action in ("guess", "exact"):
        solved = set(state["solved"])
        guess = str(data.get("guess", "")).strip()
        outcome = match_guess(guess, quiz.players, solved | revealed_indices(state))
        if action == "exact" and outcome.result != MatchResult.EXACT:
            return {"status": "not_exact"}, 200
        start_score(state, quiz)
        if outcome.result in (MatchResult.EXACT, MatchResult.CORRECT):
            index = outcome.player_index
            solved.add(index)
            state["solved"] = sorted(solved)
            answer_data(state)["solve_order"].append({
                "index": index,
                "clue_count": len(answer_data(state)["clues"].get(str(index), [])),
            })
            if not state["score_frozen"]:
                state["score_correct"] += 1
                if state["score_correct"] >= state["score_total"]:
                    state["score_frozen"] = True
            completed = game_completed(quiz, state)
            if completed:
                state["score_frozen"] = True
            result = {
                "status": "correct", "message": "Correct!",
                "player": public_player(quiz, quiz.players[index], index),
                "solved_count": len(solved), "total": quiz.total_players, "completed": completed,
            }
            if completed:
                result["share_text"] = share_result_text(quiz, state)
            return result, 200
        if outcome.result == MatchResult.NEAR:
            return {"status": "near", "message": "Close but not quite.", "score": outcome.score}, 200
        return {"status": "wrong", "message": "Not a match. Keep trying."}, 200

    if action == "clue":
        types = [value for value in data.get("types", []) if value in ("years", "initials", "nationality")]
        if not types:
            return {"status": "error", "message": "Choose at least one clue."}, 400
        answers = answer_data(state)
        if ads_enabled:
            if not answers.get("clue_unlocked"):
                return {"status": "ad_required", "message": "Watch an ad to unlock clues!"}, 403
            answers["clue_unlocked"] = False
        start_score(state, quiz)
        state["score_frozen"] = True
        target = data.get("index")
        try:
            indices = range(len(quiz.players)) if target in (None, "all") else [int(target)]
        except (TypeError, ValueError):
            return {"status": "error", "message": "Choose a valid player."}, 400
        unavailable = set(state["solved"]) | revealed_indices(state)
        indices = [index for index in indices if 0 <= index < len(quiz.players) and index not in unavailable]
        if "nationality" in types and not any(quiz.players[index].has_nationality for index in indices):
            types.remove("nationality")
        if not types:
            return {"status": "error", "message": "That clue is not available."}, 400
        clues = []
        for index in indices:
            player = quiz.players[index]
            player_clues = answers["clues"].setdefault(str(index), [])
            for kind in types:
                if kind == "nationality" and not player.has_nationality:
                    continue
                if kind not in player_clues:
                    player_clues.append(kind)
            clues.append({
                "index": index,
                **{kind: player.clue_value(kind, quiz.home_team, quiz.away_team)
                   for kind in player_clues if kind in ("years", "initials", "nationality")
                   and (kind != "nationality" or player.has_nationality)},
            })
        return {"status": "ok", "clues": clues}, 200

    if action == "giveup-answer":
        index = data.get("index")
        if data.get("confirm") is not True:
            return {"status": "error", "message": "Confirm before revealing this answer."}, 400
        if type(index) is not int or not 0 <= index < quiz.total_players:
            return {"status": "error", "message": "Choose a valid player."}, 400
        if index in state["solved"] or state["given_up"]:
            return {"status": "error", "message": "This answer is already resolved."}, 409
        start_score(state, quiz)
        revealed = answer_data(state).setdefault("revealed", [])
        if index not in revealed:
            revealed.append(index)
            revealed.sort()
        completed = game_completed(quiz, state)
        if completed:
            state["score_frozen"] = True
        result = {
            "status": "answer_revealed", "player": public_player(quiz, quiz.players[index], index),
            "solved_count": len(state["solved"]), "total": quiz.total_players, "completed": completed,
        }
        if completed:
            result["share_text"] = share_result_text(quiz, state)
        return result, 200

    if action == "giveup":
        if not data.get("confirm"):
            return {"status": "error"}, 400
        start_score(state, quiz)
        state["score_frozen"] = True
        state["given_up"] = True
        return {
            "status": "given_up",
            "players": [public_player(quiz, player, index) for index, player in enumerate(quiz.players)],
            "total": quiz.total_players, "solved_count": len(state["solved"]),
            "share_text": share_result_text(quiz, state),
        }, 200

    if action == "reset":
        if state["score_started"]:
            state["score_frozen"] = True
        state["solved"] = []
        state["given_up"] = False
        state["answer_data"] = {"clues": {}, "solve_order": []}
        return {"status": "reset"}, 200
    return {"status": "error", "message": "Unknown game action."}, 400
