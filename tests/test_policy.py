# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""VOICE.md constraints, exercised without an LLM.

The whole point of expressing the policy as prohibitions is that prohibitions are testable. These
run on plain strings against a real ParseResult, so the measurement layer is verifiable even when
no model is available — unlike the cosine metric it replaced, which needed a live LLM to produce a
number that was misleading anyway.
"""
from __future__ import annotations

import pytest

from core import analyze_sentence
from evals.policy import check
from knowledge.dictionary import attach_senses


@pytest.fixture(scope="module")
def atman_brahman():
    """`आत्मा ब्रह्म` — two technical terms English has no distinct word for."""
    return attach_senses(analyze_sentence("आत्मा ब्रह्म"))


@pytest.fixture(scope="module")
def simple():
    return attach_senses(analyze_sentence("मुनिः सत्यम् वदति"))


def _rules(violations):
    return {v.rule.split()[0] for v in violations}


# ── §4.1 identification is not metaphor ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "The atman represents brahman.",
    "The atman symbolizes brahman.",
    "The atman stands for brahman.",
])
def test_metaphor_verbs_are_flagged(bad, atman_brahman):
    assert "1" in _rules(check(bad, atman_brahman))


def test_literal_identification_passes(atman_brahman):
    assert "1" not in _rules(check("The atman is brahman.", atman_brahman))


# ── §4.2 technical terms must survive; English has no equivalent ─────────────────────────────────
def test_collapsing_a_technical_term_is_flagged(atman_brahman):
    """'The soul is God' erases both terms — the canonical milked-out rendering."""
    assert "2" in _rules(check("The soul is God.", atman_brahman))


def test_preserved_terms_pass(atman_brahman):
    assert "2" not in _rules(check("The ātman is brahman.", atman_brahman))


def test_diacritics_are_not_required(atman_brahman):
    assert "2" not in _rules(check("The atman is brahman.", atman_brahman))


# ── §4.5 no padding, hedging, editorial distance ─────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "It is said that the ātman is brahman.",
    "The ātman is, in a sense, brahman.",
    "The ātman is basically brahman.",
])
def test_padding_is_flagged(bad, atman_brahman):
    assert "5" in _rules(check(bad, atman_brahman))


# ── §4.6 no imposed devotional frame ─────────────────────────────────────────────────────────────
def test_unlicensed_devotional_vocabulary_is_flagged(simple):
    assert "6" in _rules(check("The holy sage speaks the sacred truth.", simple))


def test_plain_rendering_carries_no_violations(simple):
    assert check("The sage speaks the truth.", simple) == []


# ── the eval must not penalise the behaviour the policy demands ──────────────────────────────────
# VOICE.md §4.2 requires keeping the Sanskrit where English has no equivalent, so a faithful
# translation contains `ātman`, `kṣara`, `brahman`. An ASCII-only tokenizer split those mid-word
# (`ātman` -> `tman`) and flagged the CORRECT translation as ungrounded — the same defect as the
# cosine metric this eval replaced, which also scored the domesticated version highest.

@pytest.mark.parametrize("faithful", [
    "The ātman is brahman.",       # with diacritics
    "The atman is brahman.",       # without
    "Ātman is Brahman.",           # capitalised, as the live model renders it
])
def test_preserved_sanskrit_is_not_flagged_as_ungrounded(faithful, atman_brahman):
    assert check(faithful, atman_brahman) == []


def test_domesticated_rendering_is_still_caught(atman_brahman):
    """The canonical milked-out version must not pass just because the faithful one now does."""
    rules = _rules(check("The soul is God.", atman_brahman))
    assert "2" in rules


# ── §4.7 the rhetorical mode must survive the crossing ───────────────────────────────────────────
# The engine now computes voice and number correctly; a small model still flattens them. That is
# exactly the split the two-tier trust model is for — the structural layer is right, the LLM is
# fallible, and the policy layer catches it mechanically rather than hoping.

@pytest.fixture(scope="module")
def dual_sentence():
    return attach_senses(analyze_sentence("मुनी गच्छतः"))


@pytest.fixture(scope="module")
def passive_sentence():
    return attach_senses(analyze_sentence("रामेण ओदनः पच्यते"))


def test_collapsed_dual_is_flagged(dual_sentence):
    """English has no dual form, so preserving the distinction means saying it."""
    assert "7" in _rules(check("The sage goes.", dual_sentence))


def test_preserved_dual_passes(dual_sentence):
    assert "7" not in _rules(check("The two sages go.", dual_sentence))


def test_flattened_passive_is_flagged(passive_sentence):
    """A passive rendered active moves the kartā out of the grammatical subject."""
    assert "7" in _rules(check("Rama cooks the rice.", passive_sentence))


def test_preserved_passive_passes(passive_sentence):
    assert "7" not in _rules(check("The rice is cooked by Rama.", passive_sentence))
