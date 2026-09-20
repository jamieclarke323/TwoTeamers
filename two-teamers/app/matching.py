from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from rapidfuzz import fuzz

CORRECT_THRESHOLD = 90
NEAR_THRESHOLD = 70
MIN_GUESS_LENGTH = 3
TRANSLITERATIONS = str.maketrans({"ð": "d", "Ð": "d", "þ": "th", "Þ": "th", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l"})


class MatchResult(Enum):
    EXACT = "exact"
    CORRECT = "correct"
    NEAR = "near"
    WRONG = "wrong"


@dataclass(frozen=True)
class GuessOutcome:
    result: MatchResult
    player_index: int | None = None
    score: int = 0


def normalise(value: str) -> str:
    value = value.translate(TRANSLITERATIONS)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char)).lower()
    value = re.sub(r"['`’]", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def match_guess(guess: str, players, solved_indices: set[int]) -> GuessOutcome:
    guess_normalised = normalise(guess)
    if len(guess_normalised.replace(" ", "")) < MIN_GUESS_LENGTH:
        return GuessOutcome(MatchResult.WRONG)

    best_index = None
    best_score = 0
    for index, player in enumerate(players):
        if index in solved_indices:
            continue
        answers = [normalise(answer) for answer in player.acceptable_answers]
        if guess_normalised in answers:
            return GuessOutcome(MatchResult.EXACT, index, 100)
        score = max((round(fuzz.ratio(guess_normalised, answer)) for answer in answers), default=0)
        if score > best_score:
            best_index, best_score = index, score

    if best_index is not None and best_score >= CORRECT_THRESHOLD:
        return GuessOutcome(MatchResult.CORRECT, best_index, best_score)
    if best_index is not None and best_score >= NEAR_THRESHOLD:
        return GuessOutcome(MatchResult.NEAR, best_index, best_score)
    return GuessOutcome(MatchResult.WRONG, None, best_score)
