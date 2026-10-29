# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Data models — the word lattice, annotated stage by stage.

Plain dataclasses to stay dependency-light; swap to pydantic later if validation is wanted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Analysis:
    """Morphological analysis of a single token (one of possibly several candidates)."""
    lemma: str                          # dictionary headword (SLP1)
    pos: str                            # "noun" | "verb" | "other" | "unknown"
    features: dict[str, str] = field(default_factory=dict)  # case/number/gender or root/tense/person
    raw_tags: list[str] = field(default_factory=list)       # untouched analyzer tags, for debugging


@dataclass
class Sense:
    """A dictionary sense for a lemma."""
    source: str                         # e.g. "MW" (Monier-Williams)
    gloss: str
    #: The gender the dictionary assigns THIS sense (masculine/feminine/neuter/"any" for mfn.).
    #: None where the source records none. Optional so older callers keep working.
    gender: str | None = None


@dataclass
class Token:
    """A segmented word plus its analysis and senses."""
    id: int
    surface: str                        # Devanagari surface form
    surface_slp1: str
    analysis: Optional[Analysis] = None
    senses: list[Sense] = field(default_factory=list)


@dataclass
class KarakaEdge:
    """A semantic-role edge: `dependent` fills `role` for `head` (usually the verb)."""
    head: int                           # token id (typically the verb)
    dependent: int                      # token id (the argument)
    role: str                           # kartā | karma | karaṇa | ...


@dataclass
class ParseResult:
    """The full deterministic-core output — serializes directly to graph.json."""
    sentence_devanagari: str
    sentence_slp1: str
    tokens: list[Token] = field(default_factory=list)
    edges: list[KarakaEdge] = field(default_factory=list)

    def to_graph_dict(self) -> dict:
        return {
            "sentence_devanagari": self.sentence_devanagari,
            "sentence_slp1": self.sentence_slp1,
            "nodes": [
                {
                    "id": t.id,
                    "surface": t.surface,
                    "lemma": t.analysis.lemma if t.analysis else None,
                    "pos": t.analysis.pos if t.analysis else None,
                    "features": t.analysis.features if t.analysis else {},
                    "senses": [s.gloss for s in t.senses],
                }
                for t in self.tokens
            ],
            "edges": [asdict(e) for e in self.edges],
        }
