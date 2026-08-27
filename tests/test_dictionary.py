# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Tests for the symbolic dictionary layer (Stage 3)."""
from __future__ import annotations

import pytest

from core import analyze_sentence
from knowledge.dictionary import attach_senses, build_db, lookup


@pytest.fixture(scope="module", autouse=True)
def _fresh_db():
    build_db()  # rebuild from the seed so tests don't depend on a stale sanskrit.db


@pytest.mark.parametrize("lemma,expect", [
    ("jala", "water"),
    ("SUnya", "zero"),     # Sanskrit's own math vocabulary
    ("Atman", "self"),
    ("gam", "go"),         # verb root
])
def test_lookup_contains(lemma, expect):
    glosses = " ".join(s.gloss for s in lookup(lemma))
    assert glosses, f"no sense found for {lemma!r}"
    assert expect in glosses.lower()


def test_lookup_strips_homonym_marker():
    assert lookup("pA#1") == lookup("pA")  # 'pA' → "to drink"


def test_unknown_lemma_is_empty():
    assert lookup("zzznotaword") == []


def test_attach_senses_fills_tokens():
    result = attach_senses(analyze_sentence("बालः जलं पिबति"))
    by_lemma = {t.analysis.lemma: t.senses for t in result.tokens}
    assert any("water" in s.gloss for s in by_lemma["jala"])
    assert any("drink" in s.gloss for s in by_lemma["pA"])
