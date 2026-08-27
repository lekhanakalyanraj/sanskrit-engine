# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 3 (vector) — semantic retrieval of related verses / commentary ("essence").

The RAG half of the knowledge layer. Embedded Qdrant (local file, no Docker) + fastembed (ONNX,
no PyTorch). We embed the English *translation* side — raw-Sanskrit embeddings are weak, so per the
architecture we retrieve by meaning through English (BGE-small now; BGE-M3 multilingual is the
upgrade). This is the deterministic-core's opposite number: grammar is computed, essence retrieved.

    from knowledge.vectorstore import build_index, search, related_passages
    build_index()                       # embed the seed corpus (once)
    search("truth prevails")            # → ranked verses
    related_passages(parse_result)      # → verses related to a parsed sentence's meaning
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_CORPUS = _HERE / "corpus.yaml"
# Persisted store (gitignored). Embedded Qdrant is single-process, so a running playground would
# otherwise lock out pytest — tests set SANSKRIT_QDRANT=":memory:" to stay hermetic.
_QDIR = os.environ.get("SANSKRIT_QDRANT", str(_HERE / "qdrant"))
_COLLECTION = "corpus"
_MODEL = "BAAI/bge-small-en-v1.5"  # English; swap for BAAI/bge-m3 (multilingual) at scale

_PAYLOAD_KEYS = ("id", "sanskrit_dev", "iast", "translation", "source", "theme")
_client = None
_embedder = None


def client():
    global _client
    if _client is None:
        import atexit

        from qdrant_client import QdrantClient
        # ":memory:" is the location arg, not a path — used by tests for isolation
        _client = QdrantClient(":memory:") if _QDIR == ":memory:" else QdrantClient(path=str(_QDIR))
        atexit.register(close)  # close cleanly before teardown — avoids a native crash in __del__
    return _client


def close() -> None:
    """Close the embedded Qdrant client (call before process exit to avoid a teardown crash)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:  # noqa: BLE001
            pass
        _client = None


def _embed(texts: list[str]) -> list[list[float]]:
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(_MODEL)
    return [v.tolist() for v in _embedder.embed(texts)]


def build_index() -> int:
    """Embed the seed corpus into Qdrant (recreates the collection). Returns #passages."""
    from qdrant_client.models import Distance, PointStruct, VectorParams

    entries = yaml.safe_load(_CORPUS.read_text(encoding="utf-8")) or []
    vecs = _embed([e["translation"] for e in entries])  # embed the English side
    c = client()
    if c.collection_exists(_COLLECTION):
        c.delete_collection(_COLLECTION)
    c.create_collection(_COLLECTION, vectors_config=VectorParams(size=len(vecs[0]), distance=Distance.COSINE))
    c.upsert(_COLLECTION, points=[
        PointStruct(id=i, vector=vecs[i], payload={k: e.get(k) for k in _PAYLOAD_KEYS})
        for i, e in enumerate(entries)
    ])
    return len(entries)


def _ensure_index() -> None:
    if not client().collection_exists(_COLLECTION):
        build_index()


def search(query: str, k: int = 3) -> list[dict]:
    """Top-k corpus passages semantically closest to `query`, with similarity scores."""
    _ensure_index()
    hits = client().query_points(_COLLECTION, query=_embed([query])[0], limit=k).points
    return [{"score": round(h.score, 3), **(h.payload or {})} for h in hits]


def query_text(parse_result) -> str:
    """Build an English query from a parsed sentence's dictionary senses (content words)."""
    parts = []
    for t in parse_result.tokens:
        if t.senses:
            parts.append(t.senses[0].gloss.split(";")[0].split(",")[0].strip())
    return " ".join(parts)


def related_passages(parse_result, k: int = 3) -> list[dict]:
    """Verses whose meaning is closest to a parsed sentence (via its glosses)."""
    q = query_text(parse_result)
    return search(q, k=k) if q else []


if __name__ == "__main__":
    print(f"indexed {build_index()} passages")
    for q in ("truth conquers all", "knowledge and learning", "do your work without attachment"):
        print(f"\nQ: {q}")
        for h in search(q):
            print(f"  {h['score']}  {h['source']:22s} {h['translation']}")
