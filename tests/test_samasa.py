# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Compound decomposition — for meaning, not for grammar."""
from __future__ import annotations

import pytest

from core.samasa import decompose, explain


# ── simple words must never be pulled apart ─────────────────────────────────────────────────────
# MW lists two-letter fragments as entries, so a permissive splitter turns `gaja` ("elephant") into
# `ga` + `ja`. This is the same failure that once made `banam` look like a valid word.
@pytest.mark.parametrize("word", ["gaja", "muni", "putra", "jala", "Darma", "kzetra",
                                  "kzetre", "yuyutsavas"])
def test_simple_words_do_not_decompose(word):
    assert decompose(word) is None


# ── real compounds do ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("compound, members", [
    # the case a reader actually hit: MW glosses the whole word "a man of piety and virtue"
    ("Darmakzetre", ("Darma", "kzetre")),
    ("rAjaputra", ("rAja", "putra")),
    ("tattvajYAnAt", ("tattva", "jYAnAt")),
    ("duHKajanma", ("duHKa", "janma")),
])
def test_compounds_decompose(compound, members):
    assert decompose(compound) == members


def test_only_the_last_member_is_inflected():
    """`tattvajñānāt` is tattva (bare stem) + jñānāt (ablative). The asymmetry is what makes the
    split checkable rather than a guess."""
    assert decompose("tattvajYAnAt")[-1].endswith("At")


def test_explain_is_safe_for_display():
    """Display code should never have to handle None."""
    assert explain("gaja") == ("gaja",)
    assert explain("rAjaputra") == ("rAja", "putra")


def test_fewest_members_wins():
    """`rājaputra` is rāja+putra, never rā+ja+pu+tra."""
    assert len(decompose("rAjaputra")) == 2
