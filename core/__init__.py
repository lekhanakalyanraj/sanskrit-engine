# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Deterministic Sanskrit understanding core.

Public entry point:
    from core import analyze_sentence
    result = analyze_sentence("बालः फलं खादति")   # → ParseResult (tokens + kāraka edges)
"""
from .models import Analysis, KarakaEdge, ParseResult, Sense, Token
from .normalize import to_devanagari, to_iast, to_slp1
from .pipeline import analyze_sentence

__all__ = [
    "analyze_sentence",
    "ParseResult", "Token", "Analysis", "KarakaEdge", "Sense",
    "to_slp1", "to_devanagari", "to_iast",
]
