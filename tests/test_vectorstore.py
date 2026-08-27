# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Tests for the vector retrieval layer (Stage 3, semantic).

Slower than the core tests (loads an embedding model once). Asserts that clearly on-topic queries
surface the right seed verse in the top results — not exact ranks, to stay robust to the model.
"""
from __future__ import annotations

import pytest

from knowledge.vectorstore import build_index, search


@pytest.fixture(scope="module", autouse=True)
def _index():
    build_index()


def _ids(query, k=3):
    return [h["id"] for h in search(query, k=k)]


def test_truth_query_finds_satya():
    assert "satyameva-jayate" in _ids("truth prevails over falsehood")


def test_knowledge_query_finds_vidya():
    assert "vidya-vinaya" in _ids("education, learning and knowledge")


def test_effort_query_finds_udyama():
    assert "udyamena" in _ids("hard work and effort accomplish goals")


def test_search_returns_scored_payloads():
    hits = search("yoga and action", k=2)
    assert len(hits) == 2
    assert all("translation" in h and "score" in h and "source" in h for h in hits)
