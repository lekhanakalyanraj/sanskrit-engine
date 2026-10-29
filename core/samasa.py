# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Samāsa — decomposing compounds for MEANING, not for grammar (2.1–2.2).

The distinction that makes this safe: sandhi joins **separate words**, so stage 2 must split them
apart. A samāsa makes **one word** — it takes one case ending and fills one kāraka role — so it must
NOT be split there. What it needs is decomposition for the reader.

Without this, `dharmakṣetre` is looked up whole in Monier-Williams and comes back "a man of piety
and virtue", a rare metaphorical entry, instead of "in the field of dharma". **22% of all tokens in
real Sanskrit are compound members**, so this is the largest single gap in what the engine reports.

Only the FINAL member carries inflection; everything before it is a bare stem (prātipadika). That
asymmetry is what makes the split checkable rather than a guess.

Deliberately NOT attempted here: samāsa **type** (tatpuruṣa vs bahuvrīhi vs dvandva), which changes
the meaning — `rājaputra` is "king's son" or "one whose son is a king" depending on it. Type needs
agreement with a word outside the compound, which is the sentence structure Phase A concluded we do
not have. Splitting the members is honest; guessing the relation between them would not be.
"""
from __future__ import annotations

from functools import lru_cache

from .morphology import analyze_candidates, is_valid_word
from .segment import _underlying

#: A member shorter than this is a fragment, not a stem. At 2 characters MW's junk entries act as
#: morphemes and `gaja` ("elephant") decomposes into `ga` + `ja` — the same failure that once made
#: `banam` look like a valid word. Sanskrit stems are essentially always 3+ characters.
_MIN_MEMBER = 3
#: Beyond this the search is finding fragments, not morphemes. Real compounds do run longer (DCS
#: has a 17-member one), but those decompose in stages rather than in a single flat search.
_MAX_MEMBERS = 6


def _stem(form: str) -> bool:
    """Is this a real prātipadika — a stem — rather than a fragment the lexicon happens to contain?

    This is what separates a compound member from debris. MW lists `kṣe` and `tsu`, so a test based
    on lexicon membership alone splits `kṣetre` into `kṣe`+`tre` and the desiderative `yuyutsavaḥ`
    into `yuyu`+`tsu`. Requiring a Basic prātipadika whose lemma is the form itself rejects both
    while keeping `dharma`, `kṣetra`, `tad`, `sat`, `rāja`, `putra`.
    """
    from .morphology import kosha
    for entry in (kosha().get(form) or []):
        pe = getattr(entry, "pratipadika_entry", None)
        if pe is not None and getattr(pe, "dhatu_entry", None) is None \
                and getattr(pe, "lemma", None) == form:
            return True
    return False


def _is_word(form: str) -> bool:
    """A real word, not merely a string the lexicon contains.

    Kosha membership alone is too weak — it accepts fragments, so any string "decomposes". A
    genuine morphological analysis is the stronger test.
    """
    if len(form) < _MIN_MEMBER:
        return False
    base = _underlying(form) or form
    return any(c.pos in ("noun", "verb", "particle") for c in analyze_candidates(base))


@lru_cache(maxsize=4096)
def decompose(word_slp1: str) -> tuple[str, ...] | None:
    """Members of a compound, or None when the word is not one.

    Fewest members wins: `rājaputra` is rāja+putra, never rā+ja+pu+tra. A word that already stands
    on its own is returned as-is rather than pulled apart.
    """
    if len(word_slp1) < 2 * _MIN_MEMBER:
        return None
    # No whole-word veto: `dharmakṣetre` IS in the kosha and still needs reading compositionally,
    # since MW glosses it "a man of piety and virtue". Safety comes from `_stem` below instead —
    # every non-final member must be a real prātipadika, which is what stops `kṣetre` becoming
    # `kṣe`+`tre` without also blocking genuine compounds.

    best: tuple[str, ...] | None = None

    def search(rest: str, acc: list[str]) -> None:
        nonlocal best
        if len(acc) >= _MAX_MEMBERS:
            return
        if best is not None and len(acc) >= len(best):
            return                                   # cannot beat the incumbent
        # the tail must be the inflected final member
        if len(rest) >= _MIN_MEMBER and _is_word(rest) and acc:
            candidate = (*acc, rest)
            if best is None or len(candidate) < len(best):
                best = candidate
        for cut in range(_MIN_MEMBER, len(rest) - _MIN_MEMBER + 1):
            head = rest[:cut]
            if _stem(head):                      # a member, not a fragment
                search(rest[cut:], [*acc, head])

    search(word_slp1, [])
    return best


def explain(word_slp1: str) -> tuple[str, ...]:
    """Members if this is a compound, else the word itself — safe for display code."""
    return decompose(word_slp1) or (word_slp1,)
