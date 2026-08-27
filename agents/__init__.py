# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Agentic layer (Stage 4) — grounded explanation over the deterministic structure + retrieval.

`understand(sentence)` ties the whole engine together:
    core (structure) → dictionary (meaning) → vector (essence) → explain → verify

The LLM only phrases and checks; it never does grammar (deterministic) or invents facts
(grounded in the dictionary + retrieved passages). Orchestration is plain Python — the flow is a
fixed pipeline, not autonomous agents (see ARCHITECTURE.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core import analyze_sentence
from core.models import ParseResult
from knowledge.dictionary import attach_senses
from knowledge.vectorstore import related_passages
from llm import chat_structured

from .explainer import Explanation, LLMStructured, build_grounding, explain
from .verifier import Verdict, deterministic_signals, verify


@dataclass
class Understanding:
    """The full result of understanding a sentence — structure, meaning, essence, reading, trust."""
    result: ParseResult
    passages: list[dict] = field(default_factory=list)
    explanation: Explanation | None = None
    verdict: Verdict | None = None


def understand(sentence: str, *, k_passages: int = 3, llm: LLMStructured = chat_structured) -> Understanding:
    """Run the whole pipeline end to end. `llm` is injectable for testing without a live model."""
    result = analyze_sentence(sentence)
    attach_senses(result)
    passages = related_passages(result, k=k_passages)

    grounding = build_grounding(result, passages)
    explanation = explain(result, passages, llm=llm)
    verdict = verify(explanation, grounding, result, llm=llm)
    return Understanding(result=result, passages=passages, explanation=explanation, verdict=verdict)


__all__ = [
    "understand", "Understanding",
    "explain", "verify", "build_grounding", "deterministic_signals",
    "Explanation", "Verdict",
]
