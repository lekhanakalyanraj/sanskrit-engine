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


# The translation policy (VOICE.md). Framed as prohibitions on purpose: a milked-out translation
# is the result of INTERVENING — turning identification into metaphor, resolving tensions the
# source leaves open, flattening distinct technical terms, shrinking scale for the reader. Banning
# the interventions is truer to the text, and far more reliable for a small model than a positive
# style target, which it would answer with purple mysticism.
_SYSTEM = (
    "You render Sanskrit into English. You are a translator, not a commentator: carry the sentence "
    "across without domesticating it. The grammar is already analysed for you — each word comes "
    "with its karaka (semantic role), its grammar in [brackets], and its full range of dictionary "
    "senses. The bracketed grammar is derived from Panini's rules and is not optional detail: "
    "it tells you the tense, the mood, the number and the VOICE, and the English must carry "
    "them.\n"
    "\n"
    "CHOOSING SENSE: pick the sense the sentence actually calls for, NOT automatically the first "
    "one listed. Where a word genuinely carries more than one live sense at once, let the English "
    "carry both rather than quietly picking one.\n"
    "\n"
    "These rules are absolute:\n"
    "1. When the text identifies, the English identifies. Render 'I am X' as 'I am X' - never "
    "'represents', 'symbolizes' or 'stands for'.\n"
    "2. Never collapse two technical terms into one English word. atman, brahman, purusha, "
    "prakriti, kshara, akshara, dharma, karma and the gunas are distinct. Where English has no "
    "distinct equivalent, KEEP THE SANSKRIT WORD rather than assert a false one.\n"
    "3. If the source leaves a duality open - being/non-being, perishable/imperishable, "
    "action/inaction - leave it open. Do not resolve it on the text's behalf.\n"
    "4. Keep scale. Do not shrink a cosmic or technical statement into a comforting human-sized "
    "analogy.\n"
    "5. No padding: no 'it is said that', no hedging, no explanatory aside inside the translation. "
    "Render an assertion as an assertion.\n"
    "6. Do not impose a devotional or moralising frame on a text that carries none - and do not "
    "strip one from a text that does.\n"
    "7. Preserve the rhetorical mode: enumeration stays enumeration, a question stays a question, "
    "a command stays a command. Do not restructure into tidy argued prose.\n"
    "   PASSIVE STAYS PASSIVE. If the verb is marked [passive], the karta is in the instrumental "
    "and the English must be passive too: 'the rice is cooked by Rama', never 'Rama cooks the "
    "rice'. The two say different things about what the sentence is about.\n"
    "   A DUAL IS NOT A PLURAL. Sanskrit distinguishes two from many; if a word is marked [dual], "
    "say 'the two X' rather than letting English flatten it.\n"
    "8. Do not simplify away genuine difficulty. If the line is dense, the English is dense.\n"
    "\n"
    "Use ONLY the given words, roles and senses. Do not add entities, places, times or qualities "
    "that no given word supplies, and do not rely on outside knowledge of any text. If the input "
    "is insufficient to translate, say so plainly instead of guessing."
)


def _role(result: ParseResult, token) -> str:
    if token.analysis and token.analysis.pos == "verb":
        return "action (the verb)"
    for e in result.edges:
        if e.dependent == token.id:
            return e.role
    return "—"


_MAX_SENSES = 6

# A word's senses are not equally useful. Proper-name entries ("N. of a son of Kuru") and glosses
# still carrying apparatus are technically correct but crowd out the sense a reader needs, and the
# model tends to take whatever is listed first — so order matters as much as content.
def _gloss_rank(sense, gloss: str, index: int) -> tuple:
    """Order senses for the model. ENTRY ORDER is the primary signal — MW lists the principal
    sense first — so we only demote entries that are clearly not what a reader wants: proper-name
    entries ("N. of a son of Kuru"), leftover apparatus, and bare fragments. Sorting by length
    was tried and is wrong: it surfaces scraps like "evil i, 10" over "not being, not existing".
    """
    is_seed = sense.source != "MW"                       # curated and Apte glosses are reliable
    proper_name = gloss.startswith(("N. of", "Name of", "name of"))
    # A short gloss is not automatically a scrap. "hand" is the BEST gloss for `hasta`, and a
    # length test demoted it below "the trunk of an elephant" — the same length-based mistake this
    # function's own docstring warns against. A scrap is short AND malformed: leftover apparatus
    # like "evil i, 10", not a clean word.
    words = gloss.replace(",", " ").replace(";", " ").split()
    clean_short = bool(words) and all(w.replace("-", "").isalpha() for w in words)
    fragment = gloss.startswith("(") or (len(gloss) < 12 and not clean_short)
    residue = sum(gloss.count(ch) for ch in "[]{}")
    return (0 if is_seed else 1, 1 if proper_name else 0, 1 if fragment else 0, residue, index)


def senses_for(token, limit: int = _MAX_SENSES) -> list[str]:
    """A word's distinct dictionary senses — its semantic RANGE, not just sense #1.

    Passing only the first sense was the single biggest cause of flat, generic readings: `muni`
    has 19 senses, `dharma` 30, `yoga` 38, and MW's first entry is sometimes a cross-reference
    rather than a meaning. The explainer needs the spread to choose what the sentence actually
    calls for — and to show the reader where a word's meaning genuinely reaches.
    """
    seen, ranked = set(), []
    for sense in token.senses:
        gloss = sense.gloss.strip()
        key = gloss.lower()[:40]
        if not gloss or key in seen:
            continue
        seen.add(key)
        ranked.append((_gloss_rank(sense, gloss, len(ranked)), gloss))
    ranked.sort(key=lambda pair: pair[0])
    return [gloss for _, gloss in ranked[:limit]]


#: feature order kept stable so the grounding text is deterministic run to run
_VERB_FEATURES = ("tense", "person", "number", "voice")
_NOUN_FEATURES = ("case", "number")


def samasa_members(token) -> list[str]:
    """Compound members, or [] — a compound stays ONE grammatical word but its parts carry meaning."""
    from core.samasa import decompose
    if not token.analysis:
        return []
    found = decompose(token.analysis.lemma) or decompose(token.surface_slp1)
    return list(found) if found else []


def _grammar(token) -> str:
    """The grammar the translation must not silently drop.

    The grounding used to carry only lemma, role and senses — so `gacchati` ("he goes") and
    `gacchatu` ("let him go") reached the model identically, and it had to guess the mood. Sanskrit
    also has a DUAL, which English has no form for: VOICE.md forbids collapsing what the source
    distinguishes, and the model cannot preserve a distinction it was never shown.
    """
    if not token.analysis:
        return ""
    keys = _VERB_FEATURES if token.analysis.pos == "verb" else _NOUN_FEATURES
    vals = [token.analysis.features[k] for k in keys if token.analysis.features.get(k)]
    return f"  [{', '.join(vals)}]" if vals else ""


def build_grounding(result: ParseResult) -> str:
    """The structure + full semantic range the LLM must stay faithful to."""
    lines = ["Words in this sentence (surface — kāraka role — grammar — dictionary senses):"]
    for t in result.tokens:
        lemma = t.analysis.lemma if t.analysis else "?"
        lines.append(f"\n  {t.surface} ({to_iast(lemma)}) — {_role(result, t)}{_grammar(t)}")
        members = samasa_members(t)
        if members:
            # 22% of tokens are compound members. Looked up whole, `dharmakṣetra` returns MW's rare
            # metaphorical entry "a man of piety and virtue" instead of "field of dharma".
            lines.append(f"      compound: {' + '.join(to_iast(m) for m in members)}")
        senses = senses_for(t)
        if senses:
            for i, gloss in enumerate(senses, 1):
                lines.append(f"      {i}. {gloss}")
        else:
            lines.append("      (no dictionary meaning found)")
    return "\n".join(lines)


def explain(result: ParseResult, *, llm: LLMStructured = chat_structured) -> Explanation:
    """Produce a grounded Explanation for a parsed, sense-attached sentence."""
    grounding = build_grounding(result)
    user = (
        f"Sentence: {result.sentence_devanagari}\n\n{grounding}\n\n"
        "Render this sentence into English under the rules above, then give a one-sentence plain "
        "reading of who does what to whom (and by what means, if applicable)."
    )
    return llm(_SYSTEM, user, Explanation)
