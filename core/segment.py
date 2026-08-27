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


@lru_cache(maxsize=4096)
def _underlying(word: str) -> str | None:
    """A pausa-final word's kosha-valid underlying form (visarga → s/r, anusvāra → m)."""
    forms = [word]
    if word.endswith("H"):
        forms += [word[:-1] + "s", word[:-1] + "r"]
    if word.endswith("M"):
        forms += [word[:-1] + "m"]
    return next((f for f in forms if is_valid_word(f)), None)


def _better(cand: list[str], best: list[str] | None) -> bool:
    """Prefer fewer segments, then a longer leading word (longest-match)."""
    if best is None:
        return True
    return (len(cand), -len(cand[0])) < (len(best), -len(best[0]))


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
        for sp in _splitter().split_at(s, i):
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
    """Segment an SLP1 sentence into component words (deterministic, rule-based)."""
    words: list[str] = []
    for chunk in text_slp1.split():
        seg = _search(chunk, {})
        words.extend(seg if seg is not None else [chunk])
    if not words:
        raise RuntimeError(f"no segmentation for {text_slp1!r}")
    return words
