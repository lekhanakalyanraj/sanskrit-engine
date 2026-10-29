# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Chandas scansion — deterministic, so it is testable verse by verse."""
from __future__ import annotations

import pytest

from core.recite import scan


# ── fixed-pattern metres come from Vidyut's 145 vṛttas ──────────────────────────────────────────
def test_fixed_metre_is_identified():
    s = scan("कश्चित्कान्ताविरहगुरुणा स्वाधिकारात्प्रमत्तः")
    assert s.metre == "mandAkrAntA"


# ── the anuṣṭubh is COMPUTED, because it has no pattern to match ────────────────────────────────
# It carries the Gītā, the Rāmāyaṇa, the Mahābhārata and most Upaniṣads, and Vidyut's table cannot
# contain it: its pādas vary by design, with only syllables 5–7 constrained.

@pytest.mark.parametrize("label, verse", [
    ("BG 2.47", "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन"),
    ("BG 2.62", "ध्यायतो विषयान्पुंसः सङ्गस्तेषूपजायते"),
])
def test_pathya_anustubh(label, verse):
    s = scan(verse)
    assert s.metre == "anuṣṭubh"
    assert s.form == "pathyā"
    assert len(s.padas) == 2 and all(len(p) == 8 for p in s.padas)


def test_even_pada_requires_ja_gana():
    """The defining mark of the śloka: syllables 5–7 of an even pāda are L G L."""
    s = scan("कर्मण्येवाधिकारस्ते मा फलेषु कदाचन")
    assert s.padas[1][4:7] == "LGL"


# ── a Vedic verse that breaks the CLASSICAL rule is not broken ──────────────────────────────────
def test_vedic_deviation_is_reported_not_condemned():
    """Īśā 1 fails the classical constraint; Vedic anuṣṭubh is looser and it is correct as it is."""
    s = scan("ईशावास्यमिदं सर्वं यत्किञ्च जगत्यां जगत्")
    assert s.metre == "anuṣṭubh"          # still recognised as the metre
    assert s.form == "irregular"
    assert any("Vedic" in n for n in s.notes)   # explained, not merely flagged


# ── robustness: the underlying Rust classifier PANICS rather than raising ───────────────────────
@pytest.mark.parametrize("text", ["", "   ", "xyz123", "hello world"])
def test_junk_input_does_not_crash(text):
    s = scan(text)
    assert isinstance(s.pattern, str)


def test_marks_render_the_conventional_notation():
    s = scan("कर्मण्येवाधिकारस्ते मा फलेषु कदाचन")
    assert set(s.marks()) <= {"—", "⏑"}
    assert len(s.marks()) == len(s.pattern)
