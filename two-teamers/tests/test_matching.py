from types import SimpleNamespace

import pytest

from app.data_loader import ClubPlayer, QuizPlayer, nationality_flag
from app.matching import MatchResult, match_guess, normalise


def player(name="Jóhann Berg Guðmundsson"):
    record = ClubPlayer(name, "2020-2022", 50, 5)
    return QuizPlayer(name, record, record)


def test_normalisation_handles_accents_and_punctuation():
    assert normalise("Guðmundsson") == "gudmundsson"
    assert normalise("N'Guessan") == "nguessan"


def test_exact_name_is_correct():
    assert match_guess("Gudmundsson", [player()], set()).result == MatchResult.EXACT


def test_long_surnames_accept_more_spelling_differences():
    assert match_guess("Gudmundson", [player()], set()).result == MatchResult.CORRECT
    assert match_guess("Gudmanson", [player()], set()).result == MatchResult.CORRECT


@pytest.mark.parametrize("answer, correct, near", [
    ("abcdefgh", 90, 70), ("abcdefghi", 78, 65),
    ("abcd efgh", 90, 70), ("abcd efghi", 78, 65),
    ("ábcdefghi", 78, 65), ("O'abcdefg", 90, 70),
])
def test_threshold_boundaries_use_cleaned_answer_length(monkeypatch, answer, correct, near):
    p = SimpleNamespace(acceptable_answers=[answer])
    for score, expected in [
        (correct, MatchResult.CORRECT), (correct - 1, MatchResult.NEAR),
        (near, MatchResult.NEAR), (near - 1, MatchResult.WRONG),
    ]:
        monkeypatch.setattr("app.matching.fuzz.ratio", lambda *args: score)
        assert match_guess("testguess", [p], set()).result == expected


def test_qualifying_long_variant_is_not_masked_by_higher_short_variant(monkeypatch):
    players = [SimpleNamespace(acceptable_answers=["short"]), SimpleNamespace(acceptable_answers=["longanswer"])]
    monkeypatch.setattr("app.matching.fuzz.ratio", lambda guess, answer: 85 if answer == "short" else 78)
    outcome = match_guess("testguess", players, set())
    assert outcome.result == MatchResult.CORRECT
    assert outcome.player_index == 1
    assert match_guess("short", players, set()).result == MatchResult.EXACT
    assert match_guess("testguess", players, {1}).result == MatchResult.NEAR


@pytest.mark.parametrize("guess, answer, expected, score", [
    ("abcdefgxx", "abcdefghi", MatchResult.CORRECT, 78),
    ("abcdefxxx", "abcdefghi", MatchResult.NEAR, 67),
    ("abcdexxxx", "abcdefghi", MatchResult.WRONG, 56),
    ("abcdefgx", "abcdefgh", MatchResult.NEAR, 88),
    ("abcdefghx", "abcdefgh", MatchResult.CORRECT, 94),
])
def test_real_similarity_uses_answer_not_guess_length(guess, answer, expected, score):
    outcome = match_guess(guess, [SimpleNamespace(acceptable_answers=[answer])], set())
    assert outcome.result == expected
    assert outcome.score == score


def test_fuzzy_correct_is_distinct_from_exact_for_auto_submit():
    assert match_guess("Gudmundson", [player()], set()).result != MatchResult.EXACT


def test_initials_are_derived_from_each_name_part():
    assert player("Jóhann Berg Guðmundsson").initials == "J.B.G."
    assert player("Patrick van Aanholt").initials == "P.V.A."


@pytest.mark.parametrize("name, expected", [
    ("Bradley Wright-Phillips", "B.W-P."),
    ("Tal Ben Haim", "T.B.H."),
    ("Jean-Philippe Mateta", "J-P.M."),
    ("Alex Oxlade-Chamberlain", "A.O-C."),
    ("N'Golo Kante", "N.K."),
    ("  Bradley   Wright-Phillips  ", "B.W-P."),
])
def test_initials_preserve_hyphenated_name_parts(name, expected):
    p = player(name)
    assert p.initials == expected
    assert p.clue_value("initials", "Home", "Away") == expected


def test_nationality_clue_uses_flags_and_accepts_either_club_value():
    home = ClubPlayer("Player Name", "2020", 1, 0, "France")
    away = ClubPlayer("Player Name", "2021", 2, 1, "France")
    p = QuizPlayer("Player Name", home, away)

    assert p.has_nationality is True
    assert p.clue_value("nationality", "Home", "Away") == "🇫🇷 France"

    missing = QuizPlayer("Player Name", home, ClubPlayer("Player Name", "2021", 2, 1))
    assert missing.has_nationality is True
    assert missing.clue_value("nationality", "Home", "Away") == "🇫🇷 France"
    missing.home, missing.away = missing.away, missing.home
    assert missing.has_nationality is True
    assert missing.clue_value("nationality", "Home", "Away") == "🇫🇷 France"
    missing.away = missing.home
    assert missing.has_nationality is False
    assert nationality_flag("A country not mapped") == "A country not mapped"


def test_nationality_flags_use_complete_subdivision_sequences_and_text_fallback():
    assert nationality_flag("England") == "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"
    assert nationality_flag("Scotland") == "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    assert nationality_flag("Wales") == "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f"
    assert nationality_flag("Kosovo") == "Kosovo"
    home = ClubPlayer("Player Name", "2020", 1, 0, "England")
    away = ClubPlayer("Player Name", "2021", 2, 1, "Kosovo")
    p = QuizPlayer("Player Name", home, away)
    assert p.clue_value("nationality", "Home", "Away") == (
        "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f England / Kosovo"
    )


def test_nationality_aliases_deduplicate_and_keep_first_name():
    home = ClubPlayer("Player Name", "2020", 1, 0, "Ireland")
    away = ClubPlayer("Player Name", "2021", 2, 1, "Republic of Ireland")
    p = QuizPlayer("Player Name", home, away)

    assert p.clue_value("nationality", "Home", "Away") == "🇮🇪 Ireland"
    p.home, p.away = away, home
    assert p.clue_value("nationality", "Home", "Away") == "🇮🇪 Republic of Ireland"


def test_apps_and_goals_are_not_clue_types():
    p = player()
    for clue_type in ("apps", "goals"):
        try:
            p.clue_value(clue_type, "Home", "Away")
        except ValueError:
            continue
        raise AssertionError(f"{clue_type} should not be a clue type")


def test_three_part_names_allow_guessing_final_two_names():
    p = player("Patrick van Aanholt")
    assert "van Aanholt" in p.acceptable_answers
    assert match_guess("van Aanholt", [p], set()).result == MatchResult.EXACT
    assert match_guess("Aanholt", [p], set()).result == MatchResult.EXACT
    assert match_guess("Patrick van Aanholt", [p], set()).result == MatchResult.EXACT


def test_three_part_names_support_fuzzy_on_final_two_names():
    p = player("Patrick van Aanholt")
    # "van Aanhold" vs "van Aanholt" -> 1 typo across 11 chars = ~91% ratio >= 90%
    outcome = match_guess("van Aanhold", [p], set())
    assert outcome.result == MatchResult.CORRECT
