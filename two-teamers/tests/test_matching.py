from app.data_loader import ClubPlayer, QuizPlayer
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
