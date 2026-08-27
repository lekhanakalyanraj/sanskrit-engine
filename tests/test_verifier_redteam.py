# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Red-team the verifier with a LIVE model — the project's credibility claim.

The engine's trust story is: a small open model may drift, and the verifier catches it. That claim
is only worth anything if it is *tested against a real model*, not a stub. Each case below feeds
the verifier a deliberately hallucinated reading of a correctly-parsed sentence and asserts it is
flagged; a faithful control asserts we don't just reject everything.

Requires a reachable LLM (default: local Ollama). Skipped automatically when none is available, so
CI without a model stays green:

    pytest tests/test_verifier_redteam.py     # runs when Ollama is up
    pytest -m "not llm"                        # skip all live-LLM tests
"""
from __future__ import annotations

import urllib.request

import pytest

from agents.explainer import Explanation, build_grounding
from agents.verifier import verify
from core import analyze_sentence
from knowledge.dictionary import attach_senses, build_db

pytestmark = pytest.mark.llm

SENTENCE = "बालः हस्तेन अन्नं खादति"  # "the boy eats food with his hand"


def _llm_available() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = [pytest.mark.llm,
              pytest.mark.skipif(not _llm_available(), reason="no live LLM reachable")]


@pytest.fixture(scope="module")
def grounded_ctx():
    build_db()
    result = attach_senses(analyze_sentence(SENTENCE))
    return result, build_grounding(result)


def _flagged(verdict) -> bool:
    """The verifier objected in some way: not grounded, issues raised, or confidence lowered."""
    return (not verdict.grounded) or bool(verdict.issues) or verdict.confidence == "low"


@pytest.mark.parametrize("label,reading", [
    ("invented_location", "The boy eats food with his hand in the forest."),
    ("invented_entity", "The boy and his mother eat food with their hands."),
    ("swapped_roles", "The food eats the boy using a hand."),
    ("invented_detail", "The hungry boy quickly eats sweet rice with his right hand at dawn."),
])
def test_verifier_flags_hallucination(grounded_ctx, label, reading):
    result, grounding = grounded_ctx
    bad = Explanation(translation=reading, reading=reading)
    verdict = verify(bad, grounding, result)
    assert _flagged(verdict), f"verifier accepted a hallucinated reading ({label}): {verdict}"


def test_verifier_accepts_faithful_reading(grounded_ctx):
    """Control: a faithful reading should not be rejected (else the verifier is useless)."""
    result, grounding = grounded_ctx
    good = Explanation(
        translation="The boy eats food with his hand.",
        reading="The boy (agent) eats the food (object) with his hand (instrument).",
    )
    verdict = verify(good, grounding, result)
    assert verdict.grounded, f"verifier rejected a faithful reading: {verdict}"
