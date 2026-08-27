# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 4 — deterministic kāraka graph.

A Phase-1 simplification: map each nominal's vibhakti (case) to its kāraka role, and attach
every argument to the (single) finite verb. Correct for simple sentences; the case→role map is
not 1:1 in the general case — that ambiguity is what a later disambiguation layer handles.
"""
from __future__ import annotations

from .models import KarakaEdge, Token

# kāraka role → its usual English names (used when explaining, and by the verifier so an English
# role word in a reading isn't mistaken for invented content)
KARAKA_ENGLISH: dict[str, str] = {
    "kartā": "agent doer subject",
    "karma": "object patient goal",
    "karaṇa": "instrument means",
    "sampradāna": "recipient beneficiary",
    "apādāna": "source origin",
    "adhikaraṇa": "locus location place",
}

# case (vibhakti) → default kāraka role
CASE_TO_KARAKA: dict[str, str] = {
    "nominative": "kartā",      # agent
    "accusative": "karma",      # object
    "instrumental": "karaṇa",   # instrument
    "dative": "sampradāna",     # recipient
    "ablative": "apādāna",      # source
    "locative": "adhikaraṇa",   # locus
    # genitive (sambandha) and vocative are not core kārakas
}


def build_karaka_edges(tokens: list[Token]) -> list[KarakaEdge]:
    """Finite verb = head; each nominal's case → its kāraka role."""
    verb = next((t for t in tokens if t.analysis and t.analysis.pos == "verb"), None)
    if verb is None:
        return []
    edges: list[KarakaEdge] = []
    for t in tokens:
        if t is verb or not t.analysis:
            continue
        role = CASE_TO_KARAKA.get(t.analysis.features.get("case", ""))
        if role:
            edges.append(KarakaEdge(head=verb.id, dependent=t.id, role=role))
    return edges
