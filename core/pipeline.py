# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Orchestration — ties the deterministic stages into a ParseResult.

    Devanagari/IAST → SLP1 → segment → morphology → kāraka graph

Dictionary lookup (senses) is the Phase-2 knowledge layer; it's intentionally not here, so the
core stays deterministic, offline, and fast for the golden tests.
"""
from __future__ import annotations

from .disambiguate import select
from .karaka import build_karaka_edges
from .models import ParseResult, Token
from .morphology import analyze_candidates
from .normalize import to_devanagari, to_pausa, to_slp1
from .segment import segment


def analyze_sentence(sentence: str) -> ParseResult:
    """Run the deterministic core end to end. `sentence` may be Devanagari or IAST."""
    slp1 = to_slp1(sentence)
    words = segment(slp1)

    candidate_lists = [analyze_candidates(w) for w in words]
    analyses = select(candidate_lists)  # deterministic simple-clause disambiguation
    tokens = [
        Token(id=i, surface=to_devanagari(to_pausa(w)), surface_slp1=w, analysis=a)
        for i, (w, a) in enumerate(zip(words, analyses))
    ]

    edges = build_karaka_edges(tokens)
    return ParseResult(
        sentence_devanagari=to_devanagari(slp1),
        sentence_slp1=slp1,
        tokens=tokens,
        edges=edges,
    )
