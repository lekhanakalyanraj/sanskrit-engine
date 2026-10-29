# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""VOICE.md as executable constraints — the measurement that replaces cosine similarity.

Cosine similarity against a terse gold gloss scored "The sage speaks the truth" at **1.000** and
scored a layered, undomesticated reading WORSE. It optimised for exactly the milked-out translation
the policy forbids, so it had to go rather than be tuned.

VOICE.md §4 is written as eight prohibitions, deliberately, and prohibitions are testable. Most of
them need no LLM judge and no reference translation at all — which is the point: a reference
translation would smuggle one translator's choices back in as truth, and the history of Sanskrit
translation is precisely a history of confident single choices.

What is checkable here, and what is not:

  ✅ mechanical   metaphor verbs, padding/hedging, technical terms surviving, dualities kept open,
                  rhetorical mode, ungrounded content, imposed devotional frame
  ❌ not          "does not shrink cosmic scale", "does not simplify genuine difficulty" — these
                  need judgement. They are left to the human review loop (EVAL-STRATEGY Layer 5)
                  rather than approximated by a regex that would score confidently and wrongly.

These checks are PURE: no network, no model, unit-testable on plain strings.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from agents.verifier import unsupported_terms
from core.models import ParseResult

# ── VOICE §4.1 — identification is not metaphor ──────────────────────────────────────────────────
_METAPHOR = re.compile(r"\b(represents?|symboli[sz]es?|stands? for|is a (?:symbol|metaphor) (?:of|for)"
                       r"|signifies)\b", re.I)

# ── VOICE §4.5 — no padding, hedging or editorial distance INSIDE the translation ────────────────
_PADDING = re.compile(r"\b(it is said that|one might say|one could say|we could say|so to speak"
                      r"|as it were|in a sense|in a way|essentially|basically|arguably"
                      r"|in other words|that is to say|of course|needless to say"
                      r"|metaphorically|figuratively)\b", re.I)

# ── VOICE §4.2 — terms English has no distinct word for. Keep the Sanskrit; never collapse. ──────
#: SLP1 lemma -> the shapes we accept as "preserved" in the English (diacritics are stripped first).
TECHNICAL = {
    "Atman":   ("atman", "atma"),
    "brahman": ("brahman", "brahma"),
    "puruza":  ("purusa", "purusha"),
    "prakfti": ("prakrti", "prakriti"),
    "kzara":   ("ksara", "kshara"),
    "akzara":  ("aksara", "akshara"),
    "guRa":    ("guna",),
    "Darma":   ("dharma",),
    "karman":  ("karma",),
    "yajYa":   ("yajna", "yagya"),
    "mAyA":    ("maya",),
}

# ── VOICE §4.3 — a duality the source holds open stays open ──────────────────────────────────────
#: Both poles must survive. English pairs are accepted as well as the transliterations.
DUALITIES = [
    (("kzara", "akzara"), ("ksara", "kshara", "perishable"), ("aksara", "akshara", "imperishable")),
    (("sat", "asat"), ("being", "existent", "real"), ("non-being", "nonbeing", "unreal", "non-existent")),
    (("BAva", "aBAva"), ("being", "existence"), ("non-being", "nonexistence", "non-existence")),
]

# ── VOICE §4.6 — never impose a devotional frame the source does not carry ───────────────────────
_DEVOTIONAL = re.compile(r"\b(lord|god|godhead|divine|holy|sacred|blessed|worship|grace|almighty"
                         r"|thou|thee|thy)\b", re.I)

_INTERROGATIVE = {"kim", "kas", "kA", "kva", "kaTam", "kutas", "kadA", "kasmAt", "kiyat"}

# ── §4.7 — the rhetorical mode the source is in must survive the crossing ────────────────────────
#: English passive: an auxiliary plus a participle. Loose by design — this is a DETECTOR that
#: lowers confidence, never a corrector, so a false positive costs a flag and not a rewrite.
_PASSIVE_EN = re.compile(r"\b(is|are|was|were|been|being|gets?|got)\s+(?:\w+\s+){0,2}\w+(?:ed|en|n)\b", re.I)
#: English has no dual, so a translation that preserves one has to say so in words.
_DUAL_EN = re.compile(r"\b(two|both|pair|twin|couple)\b", re.I)


@dataclass
class Violation:
    rule: str          # VOICE.md constraint number
    detail: str


def _ascii(text: str) -> str:
    """Strip diacritics so `ātman`, `atman` and `Atman` compare equal."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn").lower()


def _lemmas(result: ParseResult) -> set[str]:
    return {t.analysis.lemma.split("#")[0] for t in result.tokens if t.analysis}


def check(translation: str, result: ParseResult) -> list[Violation]:
    """Every VOICE.md constraint this can decide mechanically. Empty list = nothing detectable."""
    out: list[Violation] = []
    flat = _ascii(translation)
    lemmas = _lemmas(result)

    for m in _METAPHOR.finditer(translation):
        out.append(Violation("1 identification-not-metaphor", f"{m.group(0)!r}"))

    for m in _PADDING.finditer(translation):
        out.append(Violation("5 no-padding-or-hedging", f"{m.group(0)!r}"))

    # 2. a technical term in the source must survive; English has no distinct equivalent for these
    for lemma, accepted in TECHNICAL.items():
        if lemma in lemmas and not any(a in flat for a in accepted):
            out.append(Violation("2 keep-technical-terms", f"{lemma!r} not preserved in the English"))

    # 3. if both poles are in the source, both must be in the translation
    for (a_lemma, b_lemma), a_forms, b_forms in DUALITIES:
        if a_lemma in lemmas and b_lemma in lemmas:
            has_a = any(f in flat for f in a_forms)
            has_b = any(f in flat for f in b_forms)
            if not (has_a and has_b):
                missing = a_lemma if not has_a else b_lemma
                out.append(Violation("3 hold-dualities-open",
                                     f"{a_lemma}/{b_lemma} in source; {missing} pole absent"))

    # 6. devotional vocabulary must be licensed by a sense the source actually offers
    supported = _ascii(" ".join(s.gloss for t in result.tokens for s in t.senses))
    for m in _DEVOTIONAL.finditer(translation):
        if _ascii(m.group(0)) not in supported:
            out.append(Violation("6 no-imposed-devotional-frame",
                                 f"{m.group(0)!r} unsupported by any sense"))

    # 7. rhetorical mode: a question stays a question, a passive stays passive, a dual stays two
    if lemmas & _INTERROGATIVE and "?" not in translation:
        out.append(Violation("7 preserve-rhetorical-mode",
                             "source is interrogative; translation is not"))

    # A passive rendered active changes what the sentence is ABOUT — the karta moves out of the
    # grammatical subject. Panini marks it (karmani prayoga) and we now compute it, so a flattened
    # rendering is detectable rather than a matter of taste.
    if any(t.analysis and t.analysis.features.get("voice") == "passive" for t in result.tokens):
        if not _PASSIVE_EN.search(translation):
            out.append(Violation("7 preserve-rhetorical-mode",
                                 "verb is karmaṇi (passive); the English reads active"))

    # Sanskrit distinguishes two from many. English has no dual form, so preserving the
    # distinction means saying it — otherwise the number is silently collapsed (§4.2's logic).
    if any(t.analysis and t.analysis.features.get("number") == "dual" for t in result.tokens):
        if not _DUAL_EN.search(translation):
            out.append(Violation("7 preserve-rhetorical-mode",
                                 "source is dual; the English does not mark two"))

    # traceability (PRD §7): every content word should trace to a sense, lemma or role
    for term in unsupported_terms(translation, result):
        out.append(Violation("grounding", f"{term!r} traces to no sense"))

    return out


RULES = ["1 identification-not-metaphor", "2 keep-technical-terms", "3 hold-dualities-open",
         "5 no-padding-or-hedging", "6 no-imposed-devotional-frame",
         "7 preserve-rhetorical-mode", "grounding"]
