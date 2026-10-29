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


# ── Dhātupāṭha ───────────────────────────────────────────────────────────────────────────────────
# Pāṇini's own root list, with the artha that states each root's sense. It had been on disk all
# along, referenced in one line as a boolean. Verbs anchor the kāraka graph and MW's verb entries
# are its messiest, so this is where an authoritative source matters most.

def test_dhatupatha_gives_roots_their_own_meaning():
    """`pā` is two homonymous roots — *pāne* "drink" and *rakṣaṇe* "protect" — and both are kept.
    The Sanskrit artha travels with the English so the authority is visible, not just its rendering."""
    dhatu = [s.gloss for s in lookup("pA") if s.source == "dhatupatha"]
    assert dhatu, "no Dhātupāṭha sense for pA"
    assert any("drink" in g.lower() and "pAne" in g for g in dhatu)
    assert any("protect" in g.lower() for g in dhatu)      # the second root is not lost


@pytest.mark.parametrize("prefixed, expected", [
    ("aDigam", "acquire"),      # NOT the base root's "to go"
    ("Agam", "come"),
    ("parABU", "defeat"),       # NOT "to exist"
])
def test_a_readers_dictionary_outranks_the_inherited_artha(prefixed, expected):
    """Vidyut inherits a root's artha across prefixes, so `parābhū` is listed "to exist" when it
    means "to perish". Apte and Macdonell record the prefixed sense, so they must come first."""
    first = lookup(prefixed)[0]
    assert first.source in ("apte", "macdonell", "seed")
    assert expected in first.gloss.lower()


def test_homonymous_roots_are_resolved_by_gana():
    """`kṛ` is two roots: svādi *hiṃsāyām* "to kill" and tanādi *karaṇe* "to do". The Dhātupāṭha
    lists both and cannot choose — but the morphology already did, because the inflected form came
    from one specific dhātu. Without this, the commonest verb in Sanskrit glosses as "to kill"."""
    from core import analyze_sentence
    r = attach_senses(analyze_sentence("रामः कर्म करोति"))
    verb = next(t for t in r.tokens if t.analysis and t.analysis.pos == "verb")
    assert verb.analysis.features.get("gana") == "tanAdi"
    assert "to do" in verb.senses[0].gloss


def test_panini_outranks_the_lexicographers_for_a_base_root():
    """The 19th-century dictionaries are downstream of the Dhātupāṭha, so for a base root the
    artha-nirdeśa is the authority — but only for a base root, not a prefix expansion."""
    top = [s for s in lookup("BU") if s.source != "seed"][0]
    assert top.source == "dhatupatha"
    assert "sattAyAm" in top.gloss
