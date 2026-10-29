# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Lexical correction of OCR output — pure, so it is testable without an image or a model."""
from __future__ import annotations

import pytest

from core.normalize import to_slp1
from core.ocr import suggest, validate


# ── the misreads Devanagari OCR actually makes ──────────────────────────────────────────────────
@pytest.mark.parametrize("misread, correct, confusion", [
    ("बनम्", "वनम्", "व / ब differ by one stroke"),
    ("धनम्", "धनम्", "control — this one is itself a word"),
])
def test_confusable_misread_is_caught(misread, correct, confusion):
    suspects = validate(misread)
    if to_slp1(misread) == to_slp1(correct):
        return                                  # the control: nothing to catch
    assert suspects, f"{confusion}: should have been flagged"
    assert to_slp1(correct) in suspects[0].suggestions


# ── correct text must not be flagged ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", ["वनम्", "धर्मः", "रामः", "गच्छति", "मुनिः"])
def test_real_words_are_clean(text):
    assert validate(text) == []


def test_genuine_sandhi_is_not_a_false_positive():
    """`satyameva` is satyam + eva. Sandhi joins words constantly; flagging it would make the
    correction layer useless on real text."""
    assert validate("सत्यमेव") == []


# ── garbage is flagged but not "fixed" ──────────────────────────────────────────────────────────
def test_unrecognisable_text_is_flagged_without_invention():
    suspects = validate("क्ष्व्रुडः")
    assert suspects and suspects[0].suggestions == []
    assert "not a recognisable word" in suspects[0].reason


# ── the suggestion mechanism itself ─────────────────────────────────────────────────────────────
def test_suggestions_must_stand_alone_as_words():
    """Only substitutions producing a WHOLE word count — that is what exposes a misread. A split
    into lexicon fragments does not: MW lists single letters, so `banam` "splits" into ba + nam and
    every misread would look legitimate."""
    for s in suggest("banam"):
        assert validate(s) == []


def test_no_suggestions_for_a_word_that_is_already_fine():
    assert validate("वनम्") == []


# ── an empty read must not look like a perfect one ──────────────────────────────────────────────
def test_empty_ocr_is_not_clean():
    """Zero suspect tokens is not success if nothing was read. The first version reported an empty
    OCR result as clean, which is a failure wearing the appearance of a perfect result."""
    from core.ocr import OCRResult
    assert OCRResult(text_devanagari="").clean is False
    assert OCRResult(text_devanagari="   ").empty is True
    assert OCRResult(text_devanagari="वनम्").clean is True
