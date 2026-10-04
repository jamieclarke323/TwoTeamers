from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl

QUIZ_TIMEZONE = ZoneInfo("Europe/London")
UNLOCK_HOUR = 6
PLAYABLE_HOURS = 72
MIN_ELIGIBLE_SEASON_START = 1999

LEAGUE_FILES = {
    "premier-league": "2627PremierLeagueFixtures.csv",
    "championship": "2627ChampionshipFixtures.csv",
    "league-one": "2627LeagueOneFixtures.csv",
    "league-two": "2627LeagueTwoFixtures.csv",
}
LEAGUE_NAMES = {
    "premier-league": "Premier League",
    "championship": "Championship",
    "league-one": "League One",
    "league-two": "League Two",
}
PLAYER_WORKBOOKS = {
    "premier-league": "Two Teamers - PremierLeague.xlsx",
    "championship": "Two Teamers - Championship.xlsx",
    "league-one": "Two Teamers - League One.xlsx",
    "league-two": "Two Teamers - League Two.xlsx",
}
LEAGUE_PREFIXES = {
    "premier-league": "pl",
    "championship": "ch",
    "league-one": "l1",
    "league-two": "l2",
}
CLUB_ALIASES = {
    "Brighton": "Brighton & Hove Albion",
    "Coventry": "Coventry City",
    "Hull": "Hull City",
    "Ipswich": "Ipswich Town",
    "Leeds": "Leeds United",
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Spurs": "Tottenham Hotspur",
}
WORKBOOK_SHEET_ALIASES = {
    "Brighton & Hove Albion": "Brighton",
    "Coventry City": "Coventry",
    "Norwich City": "Norwich",
    "Peterborough United": "Peterborough",
    "Chesterfield": "Chesterfield Town",
    "Tranmere Rovers": "Tranmere",
}

_EXTRA_TRANSLITERATIONS = str.maketrans(
    {"ð": "d", "Ð": "d", "þ": "th", "Þ": "th", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l"}
)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalise_name(value: str) -> str:
    value = value.translate(_EXTRA_TRANSLITERATIONS)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", value.lower())


def clean_value(value) -> str | int:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


@dataclass(frozen=True)
class ClubPlayer:
    name: str
    years: str
    apps: str | int
    goals: str | int


@dataclass
class QuizPlayer:
    name: str
    home: ClubPlayer
    away: ClubPlayer
    surname: str = field(init=False)
    acceptable_answers: list[str] = field(init=False)
    initials: str = field(init=False)

    def __post_init__(self) -> None:
        parts = self.name.split()
        self.surname = parts[-1] if parts else self.name
        self.acceptable_answers = list(dict.fromkeys([self.name, self.surname]))
        self.initials = "".join(f"{part[0].upper()}." for part in parts if part)

    def clue_value(self, clue_type: str, home_team: str, away_team: str) -> str:
        if clue_type == "apps":
            return f"{home_team}: {self.home.apps} / {away_team}: {self.away.apps}"
        if clue_type == "goals":
            return f"{home_team}: {self.home.goals} / {away_team}: {self.away.goals}"
        if clue_type == "years":
            return f"{home_team}: {self.home.years} / {away_team}: {self.away.years}"
        if clue_type == "initials":
            return self.initials
        raise ValueError(f"Unknown clue type: {clue_type}")


@dataclass
class Quiz:
    quiz_id: str
    league_id: str
    match_number: int
    matchweek: int
    fixture_date: datetime
    venue: str
    home_team: str
    away_team: str
    players: list[QuizPlayer]

    @property
    def unlock_at(self) -> datetime:
        return datetime.combine(self.fixture_date.date(), time(UNLOCK_HOUR), QUIZ_TIMEZONE)

    @property
    def lock_at(self) -> datetime:
        return self.unlock_at + timedelta(hours=PLAYABLE_HOURS)

    @property
    def total_players(self) -> int:
        return len(self.players)

    def availability(self, now: datetime | None = None) -> str:
        now = now or datetime.now(QUIZ_TIMEZONE)
        if now.tzinfo is None:
            now = now.replace(tzinfo=QUIZ_TIMEZONE)
        if now < self.unlock_at:
            return "upcoming"
        if now >= self.lock_at:
            return "expired"
        return "playable"


@dataclass(frozen=True)
class League:
    league_id: str
    name: str
    clubs: tuple[str, ...]
    enabled: bool


def _club_name(csv_name: str) -> str:
    return CLUB_ALIASES.get(csv_name, csv_name)


def _unique_season_players(sheet) -> dict[str, tuple[str, set[str], bool]]:
    players: dict[str, set[str]] = defaultdict(set)
    seasons: dict[str, set[str]] = defaultdict(set)
    current_season_players: set[str] = set()
    found_current_season = False
    for raw_row in sheet.iter_rows(min_row=3, values_only=True):
        row = tuple(raw_row) + (None,) * max(0, 5 - len(raw_row))
        try:
            player_count = int(row[3] or 0)
        except (TypeError, ValueError):
            continue
        season = str(row[2] or "").strip()
        is_current_season_row = not found_current_season and bool(season) and player_count > 0
        if is_current_season_row:
            found_current_season = True
        for value in row[4 : 4 + player_count]:
            name = str(value or "").strip()
            if name:
                key = normalise_name(name)
                players[key].add(name)
                if season:
                    seasons[key].add(season)
                if is_current_season_row:
                    current_season_players.add(key)
    return {
        key: (next(iter(names)), seasons.get(key, set()), key in current_season_players)
        for key, names in players.items()
        if len(names) == 1
    }


def _stats_players(sheet) -> tuple[dict[str, ClubPlayer], set[str]]:
    records: dict[str, list[ClubPlayer]] = defaultdict(list)
    for raw_row in sheet.iter_rows(values_only=True):
        row = tuple(raw_row) + (None,) * max(0, 6 - len(raw_row))
        name = str(row[0] or "").strip()
        years = row[1]
        if not name or years in (None, "Years", "Yrs"):
            continue
        records[normalise_name(name)].append(
            ClubPlayer(
                name=name,
                years=str(clean_value(years)),
                apps=clean_value(row[2]),
                goals=clean_value(row[4]),
            )
        )
    unique = {key: values[0] for key, values in records.items() if len(values) == 1}
    ambiguous = {key for key, values in records.items() if len(values) > 1}
    return unique, ambiguous


def _played_in_eligible_season(years: str) -> bool:
    """Return true if a season year or year range includes 1999-2000 or later."""
    season_years = [int(value) for value in re.findall(r"\d{4}", years)]
    if not season_years:
        return False
    # A single year such as 1999 means the 1999-2000 season. Ranges are
    # calendar-year bounds, so 1998-1999 is pre-cutoff while 1998-2001 spans
    # at least one eligible season.
    if len(season_years) == 1:
        return season_years[0] >= MIN_ELIGIBLE_SEASON_START
    return max(season_years) >= MIN_ELIGIBLE_SEASON_START + 1


def load_club_players(xlsx_path: str | Path, clubs: set[str]) -> dict[str, dict[str, ClubPlayer]]:
    workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    rosters: dict[str, dict[str, ClubPlayer]] = {}
    for club in sorted(clubs):
        sheet_name = WORKBOOK_SHEET_ALIASES.get(club, club)
        stats_sheet_name = f"{sheet_name}Stats"
        if sheet_name not in workbook.sheetnames:
            continue
        season_players = _unique_season_players(workbook[sheet_name])
        stats_players, ambiguous_stats = (
            _stats_players(workbook[stats_sheet_name])
            if stats_sheet_name in workbook.sheetnames
            else ({}, set())
        )
        rosters[club] = {
            key: ClubPlayer(
                name=season_players[key][0],
                years=stats_players[key].years if key in stats_players else "",
                apps=stats_players[key].apps if key in stats_players else "",
                goals=stats_players[key].goals if key in stats_players else "",
            )
            for key in season_players
            if key not in ambiguous_stats
            and any(_played_in_eligible_season(season) for season in season_players[key][1])
        }
    return rosters


def load_fixture_rows(data_dir: str | Path, league_id: str) -> list[dict[str, str]]:
    path = Path(data_dir) / LEAGUE_FILES[league_id]
    with path.open(encoding="utf-8-sig", newline="") as fixture_file:
        return list(csv.DictReader(fixture_file))


def load_all_clubs(data_dir: str | Path) -> dict[str, list[str]]:
    clubs_by_league: dict[str, list[str]] = {}
    for league_id in LEAGUE_FILES:
        rows = load_fixture_rows(data_dir, league_id)
        clubs = {_club_name(row[side].strip()) for row in rows for side in ("Home Team", "Away Team")}
        clubs_by_league[league_id] = sorted(clubs)
    return clubs_by_league


def load_quizzes(data_dir: str | Path, _legacy_xlsx_path: str | Path | None = None) -> tuple[list[League], list[Quiz]]:
    data_dir = Path(data_dir)
    clubs_by_league = load_all_clubs(data_dir)

    quizzes: list[Quiz] = []
    for league_id, workbook_name in PLAYER_WORKBOOKS.items():
        clubs = set(clubs_by_league[league_id])
        rosters = load_club_players(data_dir / workbook_name, clubs)
        prefix = LEAGUE_PREFIXES[league_id]
        for row in load_fixture_rows(data_dir, league_id):
            home_team = _club_name(row["Home Team"].strip())
            away_team = _club_name(row["Away Team"].strip())
            home_roster = rosters.get(home_team, {})
            away_roster = rosters.get(away_team, {})
            shared_names = sorted(home_roster.keys() & away_roster.keys(), key=lambda key: home_roster[key].name)
            players = [
                QuizPlayer(home_roster[key].name, home_roster[key], away_roster[key])
                for key in shared_names
            ]
            match_number = int(row["Match Number"])
            quizzes.append(
                Quiz(
                    quiz_id=f"{prefix}-{match_number}-{slugify(home_team)}-{slugify(away_team)}",
                    league_id=league_id,
                    match_number=match_number,
                    matchweek=int(row["Round Number"]),
                    fixture_date=datetime.strptime(row["Date"], "%d/%m/%Y %H:%M").replace(tzinfo=QUIZ_TIMEZONE),
                    venue=row["Location"].strip(),
                    home_team=home_team,
                    away_team=away_team,
                    players=players,
                )
            )

    quizzes.sort(key=lambda quiz: (quiz.fixture_date, quiz.match_number))
    leagues = [
        League(league_id, LEAGUE_NAMES[league_id], tuple(clubs_by_league[league_id]), league_id in PLAYER_WORKBOOKS)
        for league_id in LEAGUE_FILES
    ]
    return leagues, quizzes
