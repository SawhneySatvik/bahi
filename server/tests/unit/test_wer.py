from __future__ import annotations

from bahi.evals.wer import normalize, wer


def test_normalize_folds_currency_and_scripts() -> None:
    # observed live: Saaras renders "do sau rupaye" as "₹200"
    assert normalize("रमेश का बैलेंस ₹200 है।") == normalize("रमेश का बैलेंस दो सौ रुपये है")
    assert normalize("₹200") == "200"
    assert normalize("२०० रुपये") == "200"
    assert normalize("Do Sau rupaye!!") == "200"


def test_wer_zero_for_equivalent_transcripts() -> None:
    assert wer("Ramesh ko 200 rupaye udhaar likh do", "ramesh ko ₹200 udhaar likh do.") == 0.0


def test_wer_counts_substitutions_and_deletions() -> None:
    assert wer("a b c d", "a x c") == 0.5  # 1 sub + 1 del over 4 ref words
    assert wer("a b", "a b") == 0.0
    assert wer("", "") == 0.0
    assert wer("a", "") == 1.0
