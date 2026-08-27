# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 4 agent — the Verifier + confidence signal.

The trust guard, and the project's credibility headline. It checks the Explainer's reading is
supported ONLY by the provided structure and meanings, and produces a confidence signal that
folds in **deterministic** core signals (ambiguity, unknown words, no verb). On a low-resource
sacred language, confident wrongness is the failure mode — so uncertainty is surfaced, not hidden.

Why the verifier matters MORE with small open models: they follow "cite only what's grounded"
less rigidly, so an explicit checking pass carries the weight (see PRD §7, the two-tier trust bar).
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from core.models import ParseResult
from llm import chat_structured

LLMStructured = Callable[[str, str, type], object]
_RANK = {"low": 0, "medium": 1, "high": 2}
_NAME = {0: "low", 1: "medium", 2: "high"}


class Verdict(BaseModel):
    grounded: bool = Field(description="True iff every claim in the reading is supported by the given meanings and roles.")
    confidence: str = Field(description="One of exactly: high, medium, low.")
    issues: list[str] = Field(default_factory=list, description="Specific unsupported or doubtful claims, if any.")


_SYSTEM = (
    "You are a strict verifier for Sanskrit readings. You are given a sentence's word meanings "
    "and kāraka roles, and a proposed English reading. Check whether EVERY claim in the reading is "
    "supported by the given meanings and roles. Flag anything added, invented, or not derivable "
    "from the input. Be conservative: if a claim is not clearly supported, list it as an issue and "
    "lower the confidence."
)


def deterministic_signals(result: ParseResult) -> list[str]:
    """Core-side reasons to distrust the parse — independent of the LLM."""
    issues: list[str] = []
    if not any(t.analysis and t.analysis.pos == "verb" for t in result.tokens):
        issues.append("no finite verb was identified")
    if any(t.analysis and t.analysis.pos == "unknown" for t in result.tokens):
        issues.append("one or more words were not recognised")
    if any(not t.senses for t in result.tokens):
        issues.append("one or more words have no dictionary meaning")
    return issues


def verify(explanation, grounding: str, result: ParseResult,
           *, llm: LLMStructured = chat_structured) -> Verdict:
    """LLM grounding-check, then fold in deterministic signals (they can only LOWER confidence)."""
    user = (
        f"{grounding}\n\nProposed reading:\n"
        f"  translation: {explanation.translation}\n"
        f"  reading: {explanation.reading}\n\n"
        "Verify: is every claim supported by the meanings and roles above? List unsupported claims."
    )
    verdict = llm(_SYSTEM, user, Verdict)

    det = deterministic_signals(result)
    if det:
        verdict.issues = list(verdict.issues) + det
        # cap confidence at medium when the core is shaky; low if more than one signal
        capped = min(_RANK.get(verdict.confidence, 0), 1 if len(det) == 1 else 0)
        verdict.confidence = _NAME[capped]
        verdict.grounded = verdict.grounded and len(det) == 0
    return verdict
