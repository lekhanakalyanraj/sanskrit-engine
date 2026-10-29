# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Tests for the Stage-4 agents (explainer + verifier).

No live LLM is required: a stub `llm` callable returns canned typed objects, so grounding
construction, orchestration, and the confidence logic are all tested deterministically.
"""
from __future__ import annotations

import pytest

from agents import build_grounding, deterministic_signals, understand, verify
from agents.explainer import Explanation, explain
from agents.verifier import Verdict
from core import analyze_sentence
from knowledge.dictionary import attach_senses, build_db


@pytest.fixture(scope="module", autouse=True)
def _seed():
    build_db()


def stub_llm(system: str, user: str, schema: type):
    """Canned typed responses, branching on the requested schema."""
    if schema is Explanation:
        return Explanation(
            translation="The boy eats food with his hand.",
            reading="The boy (agent) eats the food (object) with his hand (instrument).",
        )
    if schema is Verdict:
        return Verdict(grounded=True, confidence="high", issues=[])
    raise AssertionError(f"unexpected schema {schema}")


def test_build_grounding_includes_roles_and_meanings():
    r = attach_senses(analyze_sentence("बालः हस्तेन अन्नं खादति"))
    g = build_grounding(r)
    assert "kartā" in g and "karaṇa" in g and "karma" in g   # roles
    assert "hand" in g and "food" in g.lower()               # meanings
    assert "action (the verb)" in g


def test_explain_passes_through_stub():
    r = attach_senses(analyze_sentence("बालः फलं खादति"))
    e = explain(r, llm=stub_llm)
    assert isinstance(e, Explanation) and "boy" in e.translation.lower()


def test_verbless_sentence_is_not_treated_as_unsound():
    """68% of real Sanskrit sentences have no finite verb — the copula is dropped and sastra prose
    is definitional. Flagging that marked down the majority of CORRECT parses and broke the
    calibration contract: `high` was less accurate than `low` on case."""
    r = attach_senses(analyze_sentence("बालः अन्नम्"))  # two nouns, no verb — perfectly normal
    assert deterministic_signals(r) == []


def test_verifier_caps_confidence_when_core_is_shaky():
    # An unrecognised word necessarily also has no dictionary meaning, so this fires BOTH core
    # signals and caps to `low` rather than `medium`. The two are coupled by construction.
    r = attach_senses(analyze_sentence("बालः क्ष्व्रुडः"))       # 2nd word is not a word
    e = Explanation(translation="boy, food", reading="a boy and food")
    v = verify(e, build_grounding(r), r, llm=stub_llm)        # stub claims high + grounded
    assert v.confidence == "low"                              # capped down by the core signals
    assert v.grounded is False                                # can't be grounded with a core issue
    assert any("recognised" in i for i in v.issues)


def test_understand_end_to_end_with_stub():
    u = understand("बालः हस्तेन अन्नं खादति", llm=stub_llm)
    assert u.explanation.translation and u.verdict.confidence == "high"
    assert u.result.edges and u.verdict.grounded is True
