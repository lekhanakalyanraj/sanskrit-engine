# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Golden fixtures for the dictionary reading pass.

These exist because a cleaning change silently deleted 5,853 senses and 187 passing tests noticed
nothing — none of them pinned what the cleaner *emits*. Every case below is a real string taken
from mw.tsv / ap90.tsv / md.tsv, not an invented one.

The two halves are equally load-bearing. STRIPPED proves the cleaner still removes apparatus;
PRESERVED proves it has not started eating meaning. A cleaner that passes only the first half is
the bug we already shipped once.
"""
from __future__ import annotations

import pytest

from knowledge.ingest_mw import clean_for_reading
from knowledge.quality import Reconciler, ReconciliationError, classify_rejection

# ── apparatus that MUST be removed ──────────────────────────────────────────────────────────────
STRIPPED = [
    ("a jar, RV. i, 50",                 "a jar"),           # citation
    ("Rhet. a figure of speech",         "a figure of speech"),
    ("Ved. Splendour.",                  "Splendour."),      # subject label, word kept
    ("sanná, pp. sunk down etc. .",      "sunk down etc."),  # accented headword echo
    (") ad. therefore .",                "therefore"),       # Macdonell adverb marker
    ("adv. [ ]",                         "adv."),            # empty bracket left by a cut span
]

# ── meaning that MUST survive ───────────────────────────────────────────────────────────────────
# Each of these was returned as "" or truncated by the shape-based abbreviation regex.
PRESERVED = [
    "Going.", "Wealth.", "Fire.", "Splendour.", "Affected.",
    "the god Indra.", "worship of Śiva.", "Prakṛti, Māyā, Illusion",
    "[leading beyond: pṛ] far, distant",          # etymology bracket is not apparatus
    "Beautiful, lovely.",
]


@pytest.mark.parametrize("raw,expected", STRIPPED)
def test_apparatus_is_stripped(raw, expected):
    assert clean_for_reading(raw) == expected


@pytest.mark.parametrize("gloss", PRESERVED)
def test_meaning_is_not_deleted(gloss):
    out = clean_for_reading(gloss)
    assert out, f"{gloss!r} was emptied — the cleaner is deleting meaning"
    assert out == gloss, f"{gloss!r} was altered to {out!r}"


def test_name_of_abbreviation_is_expanded():
    """`N.` means "name of" and occurs 46,910 times; stripping it loses the whole sense."""
    assert clean_for_reading("N. of Śiva") == "name of Śiva"


def test_proper_noun_at_sentence_end_survives():
    """The regression that cost 5,853 senses: 'the god Indra.' became 'the god'."""
    assert "Indra" in clean_for_reading("the god Indra.")


# ── the reconciler's own contract ───────────────────────────────────────────────────────────────
def test_reconciler_rejects_unexplained_delta():
    rec = Reconciler("t")
    rec.seen(10)
    rec.kept(4)                      # 6 rows vanished with no reason recorded
    with pytest.raises(ReconciliationError, match="unexplained"):
        rec.check()


def test_reconciler_rejects_excess_loss():
    rec = Reconciler("t", max_loss=0.10)
    rec.seen(10)
    rec.kept(8)
    for _ in range(2):
        rec.reject("junk", "cross_reference")
    with pytest.raises(ReconciliationError, match="rejected"):
        rec.check()


def test_reconciler_accepts_balanced_books():
    rec = Reconciler("t", max_loss=0.50)
    rec.seen(4)
    rec.kept(3)
    rec.reject("RV. i, 1", "cross_reference")
    rec.check()                      # must not raise


def test_rejection_reason_never_claims_kept():
    """A rejected row reported as reason 'kept' is how a length bar hid deleting real words."""
    assert classify_rejection("Sky", "Sky") == "too_short"
    assert classify_rejection("", "") == "empty_input"
    assert classify_rejection("{ }", "") == "markup_only"
