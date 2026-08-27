# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Knowledge & retrieval layer (Stage 3).

Symbolic dictionary lookup now (`dictionary`); vector RAG for essence/commentary later.
"""
from .dictionary import attach_senses, lookup

__all__ = ["lookup", "attach_senses"]
