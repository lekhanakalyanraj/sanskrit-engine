# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Curation layer — human corrections applied on top of the generated dictionary."""
from __future__ import annotations

import pytest

from knowledge import curation
from knowledge.curation import ADD, EDIT, HIDE, add_rule, remove_rule, suspicion_flags
from knowledge.dictionary import build_db, lookup

LEMMA = "BAva"


@pytest.fixture(autouse=True)
def _isolated_rules(tmp_path, monkeypatch):
    """Point curation at a throwaway file so tests never touch the real curation.yaml."""
    monkeypatch.setattr(curation, "_FILE", tmp_path / "curation.yaml")
    monkeypatch.setattr(curation, "_CACHE", None)
    build_db()
    yield


def test_suspicion_flags_spot_junk_and_pass_clean():
    assert "proper name" in suspicion_flags("N. of a son of Kuru")
    assert "markup residue" in suspicion_flags("{{Lbody=196110}}")
    assert suspicion_flags("becoming, being, existing") == []


def test_added_sense_leads():
    add_rule(LEMMA, ADD, replacement="being; the fact of existing")
    assert lookup(LEMMA)[0].gloss == "being; the fact of existing"


def test_hidden_sense_disappears():
    target = lookup(LEMMA)[0].gloss
    add_rule(LEMMA, HIDE, gloss=target)
    assert target not in [s.gloss for s in lookup(LEMMA)]


def test_edited_sense_is_replaced():
    target = lookup(LEMMA)[0].gloss
    add_rule(LEMMA, EDIT, gloss=target, replacement="CORRECTED")
    glosses = [s.gloss for s in lookup(LEMMA)]
    assert "CORRECTED" in glosses and target not in glosses


def test_undo_restores_original():
    original = len(lookup(LEMMA))
    add_rule(LEMMA, ADD, replacement="temporary")
    assert len(lookup(LEMMA)) == original + 1
    remove_rule(LEMMA, ADD, "")
    assert len(lookup(LEMMA)) == original


def test_curation_survives_reingest_of_seed():
    """Rules live in YAML, not the DB, so rebuilding the dictionary must not erase them."""
    add_rule(LEMMA, ADD, replacement="persists")
    build_db()                                   # wipes and reloads source='seed' rows
    assert "persists" in [s.gloss for s in lookup(LEMMA)]
