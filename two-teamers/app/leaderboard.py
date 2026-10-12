from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean


@dataclass(frozen=True)
class TeamStanding:
    team: str
    rank: int | None
    points: float | None
    supporters: int
    scoring_supporters: int
    games_played: int


@dataclass(frozen=True)
class FanStanding:
    rank: int
    total_ranked: int
    points: float
    games_played: int


def _score_rows(db, quizzes_by_id, matchweek: int | None):
    rows = db.execute(
        """SELECT u.id AS user_id, u.supported_team, p.quiz_id,
                  p.score_correct, p.score_total
           FROM users AS u
           JOIN progress AS p ON p.user_id = u.id
           WHERE p.score_started = 1 AND p.score_total > 0
             AND u.supported_team != 'Neutral'"""
    ).fetchall()
    for row in rows:
        quiz = quizzes_by_id.get(row["quiz_id"])
        if quiz is None:
            continue
        team = row["supported_team"]
        if matchweek is not None and quiz.matchweek != matchweek:
            continue
        yield row["user_id"], team, 100 * row["score_correct"] / row["score_total"]


def calculate_standings(db, quizzes, clubs: list[str], matchweek: int | None = None):
    quizzes_by_id = {quiz.quiz_id: quiz for quiz in quizzes}
    scores_by_user: dict[int, list[float]] = defaultdict(list)
    teams_by_user: dict[int, str] = {}
    for user_id, team, score in _score_rows(db, quizzes_by_id, matchweek):
        scores_by_user[user_id].append(score)
        teams_by_user[user_id] = team

    user_averages = {
        user_id: fmean(scores) for user_id, scores in scores_by_user.items()
    }
    users_by_team: dict[str, list[int]] = defaultdict(list)
    for user_id, team in teams_by_user.items():
        users_by_team[team].append(user_id)

    supporter_counts = {
        row["supported_team"]: row["supporters"]
        for row in db.execute(
            """SELECT supported_team, COUNT(*) AS supporters
               FROM users WHERE supported_team != 'Neutral'
               GROUP BY supported_team"""
        ).fetchall()
    }
    scored_teams = []
    for team in clubs:
        user_ids = users_by_team.get(team, [])
        if user_ids:
            points = fmean(user_averages[user_id] for user_id in user_ids)
            games_played = sum(len(scores_by_user[user_id]) for user_id in user_ids)
            scored_teams.append((team, points, len(user_ids), games_played))

    scored_teams.sort(key=lambda item: (-item[1], item[0]))
    ranks: dict[str, int] = {}
    previous_points = None
    for index, (team, points, _fans, _games) in enumerate(scored_teams, start=1):
        if previous_points is None or points != previous_points:
            current_rank = index
        ranks[team] = current_rank
        previous_points = points

    scored_by_team = {team: (points, fans, games) for team, points, fans, games in scored_teams}
    standings = []
    for team in clubs:
        scored = scored_by_team.get(team)
        standings.append(
            TeamStanding(
                team=team,
                rank=ranks.get(team),
                points=round(scored[0], 1) if scored else None,
                supporters=supporter_counts.get(team, 0),
                scoring_supporters=scored[1] if scored else 0,
                games_played=scored[2] if scored else 0,
            )
        )
    standings.sort(key=lambda row: (row.rank is None, row.rank or 0, row.team))
    return standings, user_averages, users_by_team, scores_by_user


def fan_standing(user_id: int, team: str, user_averages, users_by_team, scores_by_user):
    if user_id not in user_averages or team == "Neutral":
        return None
    ranked_users = users_by_team.get(team, [])
    position = 1 + sum(
        user_averages[candidate] > user_averages[user_id]
        for candidate in ranked_users
    )
    return FanStanding(
        rank=position,
        total_ranked=len(ranked_users),
        points=round(user_averages[user_id], 1),
        games_played=len(scores_by_user[user_id]),
    )
