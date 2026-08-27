# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 4 agent — the Explainer.

Turns the DETERMINISTIC structure (kāraka roles) + dictionary meanings (+ retrieved passages)
into a fluent, grounded English reading. The LLM's job is deliberately narrow: phrase what's
already been computed — it does NOT do grammar (deterministic) or invent facts (grounded).

Model-agnostic via llm.py (default: local Ollama). The `llm` callable is injectable so the
plumbing can be unit-tested with a stub, no live model required.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, Field

from core import to_iast
from core.models import ParseResult
from llm import chat_structured

LLMStructured = Callable[[str, str, type], object]


class Explanation(BaseModel):
    translation: str = Field(description="A faithful, natural English translation of the whole sentence.")
    reading: str = Field(description="One plain-English sentence: who does what to whom, and by what means.")


_SYSTEM = (
    "You are a careful Sanskrit reading assistant. The sentence's grammar has ALREADY been "
    "analysed deterministically: you are given each word with its kāraka (semantic role) and its "
    "dictionary meaning. Your only task is to render this into fluent, faithful English.\n"
    "Rules: use ONLY the given words, roles, and meanings. Do NOT add words, entities, or "
    "grammatical claims that are not in the input, and do NOT rely on outside knowledge of any "
    "text. If the input is insufficient to translate, say so plainly instead of guessing."
)


def _role(result: ParseResult, token) -> str:
    if token.analysis and token.analysis.pos == "verb":
        return "action (the verb)"
    for e in result.edges:
        if e.dependent == token.id:
            return e.role
    return "—"


def build_grounding(result: ParseResult, passages: list[dict] | None = None) -> str:
    """Compact text block of the structure + meanings the LLM must stay faithful to."""
    lines = ["Words (surface — role — meaning):"]
    for t in result.tokens:
        lemma = t.analysis.lemma if t.analysis else "?"
        meaning = t.senses[0].gloss if t.senses else "(no dictionary meaning found)"
        lines.append(f"  • {t.surface} ({to_iast(lemma)}) — {_role(result, t)} — {meaning}")
    if passages:
        lines.append("\nThematically related verses (context/essence only — NOT part of this sentence):")
        for p in passages[:3]:
            lines.append(f"  • {p.get('translation', '')} — {p.get('source', '')}")
    return "\n".join(lines)


def explain(result: ParseResult, passages: list[dict] | None = None,
            *, llm: LLMStructured = chat_structured) -> Explanation:
    """Produce a grounded Explanation for a parsed, sense-attached sentence."""
    grounding = build_grounding(result, passages)
    user = (
        f"Sentence: {result.sentence_devanagari}\n\n{grounding}\n\n"
        "Give a faithful English translation of the sentence, and a one-sentence plain reading "
        "of who does what to whom (and by what means, if applicable)."
    )
    return llm(_SYSTEM, user, Explanation)
