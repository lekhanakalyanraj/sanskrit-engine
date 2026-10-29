# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 1 — sandhi split / segmentation, rule-based and deterministic.

No ML, no training — aligned with the deterministic thesis. Candidates come from Vidyut's
**rule-based** sandhi splitter (`sandhi.Splitter`, built from Pāṇinian sandhi rules), validated
against the Vidyut kosha. (We deliberately do *not* use Vidyut's neural `Chedaka`.)

Sandhi splitting is the one genuinely-ambiguous stage: the rules *enumerate* valid splits but do
not decide which is intended. We resolve deterministically with a longest-match preference —
fewest segments, then the longest leading word — which is a principled heuristic, not a proof.
Where several splits are equally good, that residual ambiguity should surface as a confidence
signal (Phase 3), not be hidden.

Two pieces do the work:
  • terminal normalization — a pausa-final word (`bAlaH`, `puzpaM`) maps to its kosha key
    (`bAlas`, `puzpam`); handles the common space-separated case with no real fusion;
  • a memoized rule search — for a genuinely fused chunk, split via `Splitter.split_at` and
    recurse, keeping segments the kosha recognizes.
"""
from __future__ import annotations

from functools import lru_cache

from .morphology import DATA_DIR, is_valid_word

_SPLITTER = None
_MAX_SEGMENTS = 12  # guard against pathological recursion


def _splitter():
    global _SPLITTER
    if _SPLITTER is None:
        from vidyut.sandhi import Splitter
        _SPLITTER = Splitter.from_csv(str(DATA_DIR / "sandhi" / "rules.csv"))
    return _SPLITTER


# Single letters are listed in MW as dictionary entries ("o, the thirteenth vowel of the
# alphabet"), so a naive validity check accepts them and lets garbage splits through — that is how
# `bhāvo` became `bhās` + `vo` and `asato` became `asat` + `o`. A real word here is ≥2 characters.
_MIN_SEGMENT = 2


@lru_cache(maxsize=8192)
def _underlying(word: str) -> str | None:
    """A word's kosha-valid underlying form, undoing pausa/sandhi surface changes.

    Beyond pausa forms (visarga → s/r, anusvāra → m) this reverses **visarga sandhi before a voiced
    sound**: `asataḥ` surfaces as `asato`, and Vidyut's rule table does not generate that direction,
    so a verse like `nāsato vidyate` could never be segmented without it.
    """
    if len(word) < _MIN_SEGMENT:
        return None
    forms = [word]
    if word.endswith("H"):
        forms += [word[:-1] + "s", word[:-1] + "r"]
    if word.endswith("M"):
        forms += [word[:-1] + "m"]
    if word.endswith("o"):                      # -aḥ / -as before a voiced sound → -o
        forms += [word[:-1] + "aH", word[:-1] + "as"]
    return next((f for f in forms if is_valid_word(f)), None)


# Sanskrit's particles and common pronouns are a small CLOSED class, so listing them is a
# deterministic move, not a heuristic hack. They are the pieces sandhi most often hides: at equal
# segment count `satyam + eva` should beat `sat + yameva`, and `na + anṛtam` should beat
# `nās + nṛtam`. Without this, the tie-break is arbitrary and picks junk half the time.
_PARTICLES = frozenset("""
na ca eva vA hi tu vE iti api mA sma Kalu punar taTA yaTA atha aTa uta cet yadi
tat tvam aham sa saH te me te vayam yUyam idam adas etat kim yat asti asi
""".split())


def _score(cand: list[str]) -> tuple:
    """Lower is better: fewest segments, then the reading that recovers more known particles."""
    return (len(cand), -sum(1 for w in cand if w in _PARTICLES))


def _better(cand: list[str], best: list[str] | None) -> bool:
    return best is None or _score(cand) < _score(best)


def _search(s: str, memo: dict[str, list[str] | None]) -> list[str] | None:
    """Best segmentation of one whitespace chunk into kosha-valid words, or None."""
    if s in memo:
        return memo[s]
    memo[s] = None  # guard against cycles during recursion
    best: list[str] | None = None

    whole = _underlying(s)
    if whole is not None:
        best = [whole]

    for i in range(1, len(s)):
        try:
            splits = _splitter().split_at(s, i)
        except BaseException:                            # noqa: BLE001 — pyo3 PanicException
            # The splitter is Rust and PANICS on a non-ASCII byte rather than raising. A stray
            # Devanagari codepoint from real-world input would otherwise take the process down.
            return None
        for sp in splits:
            # Paninian phonotactics on the word boundary, before the (costlier) kosha lookup: no
            # Sanskrit word ends in `d`, so `sadgamaya` -> `sad`+`gamaya` is ruled out on sound
            # alone. Prunes ~15% of survivors and drops no correct split on the verses we track.
            if not sp.is_valid:
                continue
            first = sp.first
            if not is_valid_word(first):  # internal word: split_at already un-sandhi'd it
                continue
            rest = _search(sp.second, memo)
            if rest is None:
                continue
            cand = [first, *rest]
            if len(cand) <= _MAX_SEGMENTS and _better(cand, best):
                best = cand

    memo[s] = best
    return best


def segment(text_slp1: str) -> list[str]:
    """Segment an SLP1 sentence into component words — Pāṇinian rules and the kosha, nothing else.

    This was a hybrid: rules generated candidates, the kosha validated them, and the trained Chedaka
    broke ties. Measured against DCS, the model turned out to be pure loss — it never once produced
    a strictly shorter segmentation, and handing it ties cost **1.8 points** (65.4% -> 63.6%).

    It was actively destroying good answers. For `cAvyavasTAyAH` the rules find `ca` + `avyavasTAyAH`
    — `ca` being a known particle, which is exactly the signal the tie-break exists to use — and
    Chedaka replaced it with `cAs` + `vyavasTAyAs`, junk that the kosha happens to accept. Half of
    all boundary errors had this shape: a particle the rules had correctly peeled off and the model
    put back. `asato mā sadgamaya` was recorded as a known failure for the same reason; the rules
    always had it right.

    The docstring here used to claim the model settled `pūrṇam adaḥ` and `nāsato ... bhāvo`. That
    stopped being true once the rules learned particles, the `-o` ← `-aḥ` reversal and phonotactic
    filtering; both now parse on rules alone.
    """
    words: list[str] = []
    for chunk in text_slp1.split():
        seg = _search(chunk, {})
        words.extend(seg if seg is not None else [chunk])
    if not words:
        raise RuntimeError(f"no segmentation for {text_slp1!r}")
    return words
