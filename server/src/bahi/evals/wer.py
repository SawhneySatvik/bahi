"""Word Error Rate with a normalization pipeline applied IDENTICALLY to
reference and hypothesis (docs/metrics.md).

Normalization (in order): Unicode NFC, casefold, Devanagari digits -> ASCII,
currency folding (₹200 / 200 rupaye / २०० रुपये -> '200'), a small Hindi
number-word table (both scripts) -> digits, punctuation stripped (incl. danda),
whitespace collapsed. Known limit: number-word folding covers common shop
amounts, not general Hindi numerals — gold transcripts are authored with
digits to keep WER about *recognition*, not orthography.
"""

from __future__ import annotations

import re
import unicodedata

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# longest-first replacement of common spoken amounts
_NUMBER_WORDS = [
    ("dedh hazaar", "1500"), ("डेढ़ हज़ार", "1500"), ("डेढ़ हजार", "1500"),
    ("unnees sau", "1900"), ("उन्नीस सौ", "1900"),
    ("dhai sau", "250"), ("ढाई सौ", "250"),
    ("dedh sau", "150"), ("डेढ़ सौ", "150"),
    ("paanch sau", "500"), ("पाँच सौ", "500"), ("पांच सौ", "500"),
    ("teen sau", "300"), ("तीन सौ", "300"),
    ("chaar sau", "400"), ("चार सौ", "400"),
    ("do sau", "200"), ("दो सौ", "200"),
    ("ek sau", "100"), ("एक सौ", "100"),
    ("hazaar", "1000"), ("हज़ार", "1000"), ("हजार", "1000"),
]

_CURRENCY_WORDS = re.compile(r"(rupaye|rupees|rupya|rupay|रुपये|रुपए|रुपया|rs\.?|inr)", re.I)
_PUNCT = re.compile(r"[।,.!?;:\"'()\[\]{}\-–—]")


def normalize(text: str) -> str:
    out = unicodedata.normalize("NFC", text).casefold()
    out = out.translate(_DEVANAGARI_DIGITS)
    out = out.replace("₹", " ")
    for words, digits in _NUMBER_WORDS:
        out = out.replace(words, f" {digits} ")
    out = _CURRENCY_WORDS.sub(" ", out)
    out = _PUNCT.sub(" ", out)
    return " ".join(out.split())


def wer(reference: str, hypothesis: str) -> float:
    """Word-level edit distance / reference length, on normalized text."""
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            current[j] = min(
                previous[j] + 1,  # deletion
                current[j - 1] + 1,  # insertion
                previous[j - 1] + (ref_word != hyp_word),  # substitution
            )
        previous = current
    return previous[-1] / len(ref)
