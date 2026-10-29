# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Verse-level segmentation — the real target, and the current frontier.

The gold set is simple SVO sentences; real Sanskrit is sandhi-compressed verse. These lock in the
verses the hybrid segmenter now handles, and record the ones it still gets wrong as `xfail` so the
gap is visible rather than forgotten. An xfail that starts passing (XPASS) is a signal to promote
it into the asserted set.

Segmentation only — morphology and kāraka over verse are a later problem.
"""
from __future__ import annotations

import pytest

from core.normalize import to_slp1
from core.segment import segment


def seg(devanagari: str) -> list[str]:
    return segment(to_slp1(devanagari))


# ── verses the hybrid segmenter now parses correctly ────────────────────────
@pytest.mark.parametrize("name,verse,expected", [
    (
        "mundaka-satyameva",
        "सत्यमेव जयते नानृतं",
        ["satyam", "eva", "jayate", "na", "anftam"],
    ),
    (
        "isha-invocation-purnam",
        "पूर्णमदः पूर्णमिदं पूर्णात्पूर्णमुदच्यते",
        ["pUrRam", "adas", "pUrRam", "idam", "pUrRAt", "pUrRam", "udacyate"],
    ),
])
def test_verse_segmentation(name, verse, expected):
    assert seg(verse) == expected


def test_bg_2_16_first_half():
    """`nāsato vidyate bhāvo` — visarga-before-voiced (`asataḥ`→`asato`) and `na`+vowel."""
    assert seg("नासतो विद्यते भावो")[:4] == ["na", "asatas", "vidyate", "BAvas"]


# ── promoted from xfail when the neural ranker was removed ──────────────────
# Both of these blamed the rule splitter in their recorded reason. Both were the
# Chedaka model overriding a correct rule-based split on a tie.


# ── still-open failures: recorded, not hidden ───────────────────────────────
@pytest.mark.xfail(reason="genuine lexical ambiguity: `tattvam` IS a word (and derives from "
                          "tat+tvam). Both parses are grammatical; needs context, not rules.",
                   strict=False)
def test_tat_tvam_asi():
    assert seg("तत्त्वमसि") == ["tat", "tvam", "asi"]


def test_asato_ma_sadgamaya():
    """Recorded for months as "the splitter prefers sadgam+aya". It never did — the RULES always
    found sat+gamaya and the neural Chedaka overwrote it. Passing since the model was dropped."""
    assert seg("असतो मा सद्गमय") == ["asatas", "mA", "sat", "gamaya"]


@pytest.mark.xfail(reason="`yatkiñca` (yat+kim+ca) not split; `īśāvāsyam idaṃ` boundary missed. "
                          "Three-way particle compounds are unhandled.", strict=False)
def test_isha_upanishad_1():
    assert seg("ईशावास्यमिदं सर्वं यत्किञ्च जगत्यां जगत्") == [
        "ISAvAsyam", "idam", "sarvam", "yat", "kim", "ca", "jagatyAm", "jagat",
    ]


def test_bg_2_16_second_half():
    """Also blamed on the splitter ("yields nās+bhāvas"), also the ranker. `na`+`aBAvas` is the
    exact shape the particle tie-break is built to catch, and the model kept undoing it."""
    assert seg("नाभावो विद्यते सतः") == ["na", "aBAvas", "vidyate", "satas"]
