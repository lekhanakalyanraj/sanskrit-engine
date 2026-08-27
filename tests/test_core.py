# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Golden tests for the deterministic core.

Each gold sentence has a hand-verified expected structure; we assert the engine reproduces it
exactly. Because the core is deterministic, these are real assertions — not eval heuristics.

Run:  pytest              (from the sanskrit-engine/ directory, inside the venv)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from core import analyze_sentence

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"


def _load_gold() -> list[dict]:
    entries = []
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        for entry in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            entry["_file"] = path.name
            entries.append(entry)
    return entries


GOLD = _load_gold()


def _strip_homonym(lemma: str) -> str:
    """Lexicon marks homonyms as e.g. 'pA#1'; compare on the bare lemma."""
    return re.sub(r"#\d+$", "", lemma)


def test_gold_set_nonempty():
    assert GOLD, "no gold entries found — check gold/*.yaml"


@pytest.mark.parametrize("entry", GOLD, ids=[e["id"] for e in GOLD])
def test_core_matches_gold(entry):
    result = analyze_sentence(entry["sentence_dev"])
    got = result.tokens
    exp = entry["tokens"]

    # 1. Segmentation — exact token sequence
    assert [t.surface_slp1 for t in got] == [tk["slp1"] for tk in exp], "segmentation mismatch"

    # 2. Per-token morphology — lemma, pos, and (for nominals) case
    for g, e in zip(got, exp):
        assert g.analysis is not None, f"no analysis for {g.surface_slp1}"
        assert _strip_homonym(g.analysis.lemma) == e["lemma"], f"lemma mismatch on {e['slp1']}"
        assert g.analysis.pos == e["pos"], f"pos mismatch on {e['slp1']}"
        if "case" in e:
            assert g.analysis.features.get("case") == e["case"], f"case mismatch on {e['slp1']}"

    # 3. Kāraka graph — every expected (dependent, role) edge, and all edges point to the verb
    verb_ids = [t.id for t in got if t.analysis and t.analysis.pos == "verb"]
    assert len(verb_ids) == 1, "expected exactly one finite verb"
    got_edges = {(got[ed.dependent].surface_slp1, ed.role) for ed in result.edges}
    exp_edges = {(tk["slp1"], tk["karaka"]) for tk in exp if "karaka" in tk}
    assert got_edges == exp_edges, "kāraka edge mismatch"
    assert all(ed.head == verb_ids[0] for ed in result.edges), "an edge does not point to the verb"
