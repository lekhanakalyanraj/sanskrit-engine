# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Shared pytest configuration.

Embedded Qdrant is single-process: a running `streamlit run playground.py` holds a lock on
knowledge/qdrant/, which used to make the vector tests fail with "already accessed by another
instance". Tests therefore use an isolated **in-memory** store, so the suite is hermetic and can
run while the playground is open.

Must be set before knowledge.vectorstore is imported, hence this module-level assignment.
"""
import os

os.environ.setdefault("SANSKRIT_QDRANT", ":memory:")

os.environ.setdefault("SANSKRIT_CORPUS_SEED_ONLY", "1")
