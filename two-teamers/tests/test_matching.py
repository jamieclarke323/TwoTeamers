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


def test_ninety_percent_is_awarded_but_seventy_is_only_near():
    assert match_guess("Gudmundson", [player()], set()).result == MatchResult.CORRECT
    assert match_guess("Gudmanson", [player()], set()).result == MatchResult.NEAR


def test_fuzzy_correct_is_distinct_from_exact_for_auto_submit():
    assert match_guess("Gudmundson", [player()], set()).result != MatchResult.EXACT


def test_initials_are_derived_from_each_name_part():
    assert player("Jóhann Berg Guðmundsson").initials == "J.B.G."
    assert player("Patrick van Aanholt").initials == "P.V.A."


def test_nationality_clue_uses_flags_and_requires_both_club_values():
    home = ClubPlayer("Player Name", "2020", 1, 0, "France")
    away = ClubPlayer("Player Name", "2021", 2, 1, "France")
    p = QuizPlayer("Player Name", home, away)

    assert p.has_nationality is True
    assert p.clue_value("nationality", "Home", "Away") == "🇫🇷"

    missing = QuizPlayer("Player Name", home, ClubPlayer("Player Name", "2021", 2, 1))
    assert missing.has_nationality is False
    assert nationality_flag("A country not mapped") == "A country not mapped"


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
