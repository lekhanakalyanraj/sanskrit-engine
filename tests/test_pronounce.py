# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Pronunciation — deterministic, so it is testable to the letter."""
from __future__ import annotations

import pytest

from core.normalize import to_pausa
from core.pronounce import is_heavy, pronounce, syllabify


# ── syllables: one vowel each; a cluster splits, a single consonant carries over ─────────────────
@pytest.mark.parametrize("word, syllables", [
    ("gacCati", ["gac", "Ca", "ti"]),      # cluster cC splits: c closes, C opens
    ("mati", ["ma", "ti"]),                # single consonant opens the next syllable
    ("Darma", ["Dar", "ma"]),
    ("tat", ["tat"]),
    ("AtmA", ["At", "mA"]),
])
def test_syllabify(word, syllables):
    assert syllabify(word) == syllables


# ── weight (guru/laghu) — long vowel, or short vowel closed by a consonant ───────────────────────
@pytest.mark.parametrize("syllable, heavy", [
    ("gac", True),    # short a, closed
    ("ma", False),    # short a, open
    ("mA", True),     # long vowel
    ("maH", True),    # visarga closes it
    ("ti", False),
])
def test_weight(syllable, heavy):
    assert is_heavy(syllable) is heavy


# ── respelling: the traps an English reader falls into ──────────────────────────────────────────
@pytest.mark.parametrize("word, respelling", [
    ("Darma", "DHUR-muh"),      # short a is the vowel of "but", NOT "father"
    ("kfzRa", "KRISH-nuh"),     # ṛ is a vowel; ṣ is sh
    ("yoga", "YOH-guh"),
    ("SAnti", "SHAAN-ti"),
    ("mokza", "MOHK-shuh"),
    ("AtmA", "AAT-maa"),
])
def test_respelling(word, respelling):
    assert pronounce(word).respelling == respelling


def test_final_short_a_is_not_moo():
    """`dharma` respelt "DHUR-mu" invites the vowel of "moo"; the guide must not create a new trap."""
    assert pronounce("Darma").respelling.endswith("muh")


def test_aspirates_keep_their_h():
    """bh and b are different consonants — dropping the h changes the word."""
    assert pronounce("BagavAn").respelling.lower().startswith("bhu")


def test_sounds_english_lacks_are_named_not_faked():
    """A respelling cannot convey retroflexion, so it is stated instead of pretended."""
    assert any("retroflex" in n for n in pronounce("kfzRa").notes)


def test_uses_the_written_form():
    """`rAmas` is the kosha-facing form; what a reader says is the pausa form `rAmaH`."""
    assert pronounce(to_pausa("rAmas")).respelling == "RAA-muh"


# ── onset clusters stay together ─────────────────────────────────────────────────────────────────
# `tra`, `kra`, `sva`, `dhya` are legal Sanskrit onsets, so splitting them misplaces the consonant.
# The first version produced put-ra and kSet-re because it borrowed the METRICAL split, which
# deliberately breaks clusters to compute syllable weight. Metre and respelling need different
# divisions and `core.recite` keeps the metrical one.

@pytest.mark.parametrize("word, syllables", [
    ("putra", ["pu", "tra"]),          # not put-ra
    ("kSetre", ["kSe", "tre"]),        # not kSet-re
    ("SAstra", ["SAs", "tra"]),        # str- splits once: the onset is tra
    ("mitra", ["mi", "tra"]),
    ("gacCati", ["gac", "Ca", "ti"]),  # cC is not an onset, so it does split
    ("annam", ["an", "nam"]),
])
def test_onset_clusters_are_not_split(word, syllables):
    assert syllabify(word) == syllables


def test_medial_short_a_is_not_doo():
    """`khādati` respelt "KHAA-du-ti" reads *doo*; the trap applies medially, not just finally."""
    assert pronounce("KAdati").respelling == "KHAA-duh-ti"
