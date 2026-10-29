# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Input normalisation — the first step in cleaning any real Sanskrit data.

People write Sanskrit in a dozen romanisations and half a dozen scripts. An engine that accepts two
of them mangles the rest SILENTLY, which is worse than refusing: `kzetra` — our own internal SLP1 —
was being read as IAST and turned into `kj0etra`, and nothing anywhere said so.
"""
from __future__ import annotations

import pytest

from core.normalize import to_slp1


@pytest.mark.parametrize("scheme, text", [
    ("Devanagari",     "क्षेत्र"),
    ("IAST",           "kṣetra"),
    ("ISO 15919",      "kṣētra"),      # ē for e, and ṁ for ṃ
    ("Harvard-Kyoto",  "kSetra"),
    ("ITRANS",         "kShetra"),
    ("Velthuis",       "k.setra"),
    ("SLP1",           "kzetra"),      # our own format must survive a round trip
    ("popular ASCII",  "kshetra"),     # no diacritics — "ksh" means kṣ, not kś
    ("popular + h",    "kṣhetra"),     # the style the Gītā source uses
    ("Bengali",        "ক্ষেত্র"),
    ("Telugu",         "క్షేత్ర"),
])
def test_every_romanisation_reaches_the_same_word(scheme, text):
    assert to_slp1(text) == "kzetra", f"{scheme} was not normalised"


def test_slp1_round_trips_when_it_is_distinguishable():
    """SLP1 survives a round trip when it carries a character only SLP1 uses — z, f, x."""
    for word in ("kzetra", "Darmakzetre", "yuyutsavaH", "pfTivI"):
        assert to_slp1(word) == word


def test_bare_ascii_between_schemes_is_genuinely_ambiguous():
    """`Darma` is SLP1 *dharma* and Harvard-Kyoto *ḍarma*, and nothing in the string decides it.

    Recorded as a known limit rather than papered over: no heuristic resolves it, because the two
    schemes really do assign different sounds to the same letters. Callers that already hold SLP1
    should not round-trip it through detection.
    """
    assert to_slp1("kSetra") == "kzetra"          # read as Harvard-Kyoto
    assert to_slp1("kzetra") == "kzetra"          # `z` marks it as SLP1


def test_nukta_does_not_reach_the_splitter():
    """The nukta (़) is a Devanagari codepoint that survived transliteration into "ASCII" SLP1 and
    made Vidyut's Rust splitter PANIC — unrecoverable, on real Gītā text."""
    out = to_slp1("पितऱ्नाथ")
    assert out.isascii()


def test_empty_input_is_safe():
    assert to_slp1("") == "" and to_slp1("   ") == ""
