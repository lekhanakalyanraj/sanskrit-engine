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

import re
from typing import Callable

from pydantic import BaseModel, Field

from core.karaka import KARAKA_ENGLISH
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
    "You are a verifier for Sanskrit readings. You are given a sentence's word list (each word with "
    "its kāraka role and dictionary meaning) and a proposed English reading.\n"
    "\n"
    "PROCEDURE — do this literally:\n"
    "Go through the reading and pick out every content element: each person or thing, each place, "
    "each time, each quantity, and each descriptive word (adjective or adverb). For EACH one, find "
    "the input word that supplies it. If no input word supplies it, that element is UNSUPPORTED — "
    "list it as an issue. Extra detail is the most common failure: a place ('in the forest'), a "
    "time ('at dawn'), a manner ('quickly'), an added quality ('hungry', 'sweet', 'right'), or an "
    "extra participant ('his mother') must each come from a given word, or be flagged.\n"
    "Also flag a role reversal (e.g. the kartā/agent treated as the karma/object) and any claim "
    "that contradicts a given meaning.\n"
    "\n"
    "Do NOT flag mere wording: a synonym or paraphrase of a supplied gloss ('composes' for 'to "
    "arrange, compose, produce'), picking one sense from a gloss listing several, or natural "
    "English phrasing (articles, tense, word order).\n"
    "\n"
    "So: added CONTENT is an issue; different WORDING is not. If every content element traces to an "
    "input word and the roles are right, it is grounded with high confidence."
)


# Function words and generic connectives that carry no content — never treated as hallucinations.
_STOPWORDS = frozenset("""
a an the this that these those there here it its is are was were be been being am
he she they them his her their our your my mine ours yours i you we us me him
of to in on at by for with from into onto upon within without via as and or but nor so
not no do does did doing done has have had having will would shall should can could may might must
who whom whose which what when where why how while during after before then than
one two some any each every both all many much more most other another same such own
who's who’re thing things way ways action actions performs perform performing performed
someone something person people who’ve
""".split())

_SUFFIXES = ("ings", "ing", "ies", "ed", "es", "s", "ly")


def _variants(word: str) -> set[str]:
    """The word plus plausible stems — 'goes' → {goes, goe, go}, so it matches the gloss 'to go'."""
    out = {word}
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            out.add(word[: -len(suf)])
    return out


def _content_words(text: str) -> set[str]:
    # keep 2-letter content words: glosses like "to go, move, come" hinge on them
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) >= 2}


def unsupported_terms(reading: str, result: ParseResult) -> list[str]:
    """Content words in the reading with no basis in any token's meaning — DETERMINISTIC.

    A small model is unreliable at spotting added detail ("in the forest", "at dawn"), but the
    check itself is pure lexical work: every content word should trace to a dictionary gloss, a
    lemma, or a kāraka role name. Anything else is unsupported. No LLM required.
    """
    supported: set[str] = set()
    for token in result.tokens:
        for sense in token.senses:
            supported |= _content_words(sense.gloss)
        if token.analysis:
            supported.add(token.analysis.lemma.lower())
    for edge in result.edges:
        supported |= _content_words(edge.role)
        supported |= _content_words(KARAKA_ENGLISH.get(edge.role, ""))  # 'agent', 'instrument', …
    supported |= _content_words("verb action")  # the reading may name the verb as such
    # expand the supported vocabulary with stems, so 'composes' matches the gloss 'compose'
    supported = {v for w in supported for v in _variants(w)}

    flagged = []
    for word in sorted(_content_words(reading)):
        if _variants(word) & supported:
            continue
        # last resort: a long word containing/contained by a supported one (compose/composition)
        if any(len(s) > 3 and (word.startswith(s) or s.startswith(word)) for s in supported):
            continue
        flagged.append(word)
    return flagged


def deterministic_signals(result: ParseResult) -> list[str]:
    """HARD signals — the parse itself is unsound, so no reading over it can be trusted."""
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

    issues = list(verdict.issues)
    cap = _RANK.get(verdict.confidence, 0)

    # SOFT — a term we couldn't trace to any gloss. Often genuine added content, but sometimes just
    # a synonym ("flows" for "to go"), so it warns and caps confidence rather than failing outright.
    soft = unsupported_terms(f"{explanation.translation} {explanation.reading}", result)
    if soft:
        issues.append("terms not traceable to a word meaning (added content, or paraphrase): "
                      + ", ".join(soft))
        cap = min(cap, 1)

    # HARD — the parse is unsound, so the reading cannot be grounded whatever the LLM says.
    hard = deterministic_signals(result)
    if hard:
        issues += hard
        cap = min(cap, 1 if len(hard) == 1 else 0)
        verdict.grounded = False

    verdict.issues = issues
    verdict.confidence = _NAME[cap]
    return verdict
