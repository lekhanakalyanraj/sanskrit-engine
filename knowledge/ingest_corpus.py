# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Bulk-ingest a real verse + commentary corpus for semantic ("essence") retrieval.

Source: github.com/AdiyogiArts/gita-json (MIT) — all 700 Bhagavad Gītā verses with Devanagari,
IAST, an English translation, and a per-verse **explanation** (commentary). The commentary is what
makes essence retrieval meaningful: without it we could only match on a bare translation.

Writes a normalized `corpus_gita.json` that vectorstore.build_index() picks up alongside the
curated seed corpus (corpus.yaml). Both are gitignored/regenerable.

    python -m knowledge.ingest_corpus        # download (cached) + normalize
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BASE_URL = "https://raw.githubusercontent.com/AdiyogiArts/gita-json/main/base.json"
_EN_URL = "https://raw.githubusercontent.com/AdiyogiArts/gita-json/main/en.json"
_CACHE_BASE = _HERE / "_gita_base.json"
_CACHE_EN = _HERE / "_gita_en.json"
OUT = _HERE / "corpus_gita.json"


def _fetch(url: str, dest: Path) -> dict:
    if not dest.exists() or dest.stat().st_size < 1000:
        print(f"downloading {url.rsplit('/', 1)[-1]} …")
        urllib.request.urlretrieve(url, dest)
    return json.loads(dest.read_text(encoding="utf-8"))


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def ingest() -> int:
    base, en = _fetch(_BASE_URL, _CACHE_BASE), _fetch(_EN_URL, _CACHE_EN)
    entries = []
    for key, b in base.items():
        e = en.get(key, {})
        translation = _clean(e.get("translation", ""))
        if not translation:
            continue
        entries.append({
            "id": f"gita-{key}",
            "sanskrit_dev": _clean(b.get("sanskrit", "")),
            "iast": _clean(b.get("transliteration", "")),
            "translation": translation,
            "commentary": _clean(e.get("explanation", "")),
            "source": f"Bhagavad Gītā {b.get('chapter')}.{b.get('verse')}",
            "theme": _clean(b.get("chapterNameTranslation", "")),
        })
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(entries)


if __name__ == "__main__":
    n = ingest()
    print(f"ingested {n} verses → {OUT.name}")
    sample = json.loads(OUT.read_text(encoding="utf-8"))[46]
    print(f"\nsample: {sample['source']}\n  {sample['sanskrit_dev'][:60]}")
    print(f"  {sample['translation'][:90]}")
    print(f"  commentary: {sample['commentary'][:110]}…")
