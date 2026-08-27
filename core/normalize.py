# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 0 — transliteration / normalization to SLP1.

Accepts Devanagari OR Latin transliteration (IAST); everything downstream works in SLP1.
"""
from __future__ import annotations

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_DEVANAGARI_RANGE = ("ऀ", "ॿ")


def _looks_devanagari(text: str) -> bool:
    return any(_DEVANAGARI_RANGE[0] <= c <= _DEVANAGARI_RANGE[1] for c in text)


def to_slp1(text: str) -> str:
    """Normalize Devanagari or IAST input to SLP1."""
    scheme = sanscript.DEVANAGARI if _looks_devanagari(text) else sanscript.IAST
    return transliterate(text, scheme, sanscript.SLP1)


def to_devanagari(slp1: str) -> str:
    return transliterate(slp1, sanscript.SLP1, sanscript.DEVANAGARI)


def to_iast(slp1: str) -> str:
    return transliterate(slp1, sanscript.SLP1, sanscript.IAST)
