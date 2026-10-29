# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""LLM SENSE — a short, plain gloss per lemma, written from the model's own knowledge.

Why this exists. Seven ranking strategies have now been measured against the Gītā padapāṭha and
none beat plain source-authority order: consensus -5.5, gender matching -7.5, Lesk -2.5 to -7.1,
four source reorderings ~0. The single thing that measurably works is CURATION — particles score
62.9% against nouns at 21.9%, and that gap is produced by about thirty hand-written glosses. This
is curation at scale.

The model is given the stem ALONE. No Monier-Williams text, no verse, no context — the request was
explicitly for the model's prior knowledge rather than a rewrite of ours, and that also keeps this
an INDEPENDENT source rather than a paraphrase of one we already hold.

    python -m knowledge.ingest_llm_sense --gita     # the Gītā's vocabulary (pilot)
    python -m knowledge.ingest_llm_sense --all      # every lemma we hold

── A WARNING ABOUT MEASURING THIS ─────────────────────────────────────────────────────────────
Our only meaning benchmark is the Bhagavad Gītā, one of the most-quoted texts in existence, and
its word-by-word glosses are all over the training data of every model. A score here therefore
CANNOT distinguish "the model knows Sanskrit" from "the model memorised our answer key". Whatever
number this produces is an upper bound and must be reported as one. A clean read needs a gloss
corpus the model is unlikely to have seen; we do not currently have one.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DB = _HERE / "sanskrit.db"
_CACHE = _HERE / "llm_sense.json"

SOURCE = "llm"

#: Asks for the shape that already works: short, plain, no apparatus. The UNKNOWN escape matters —
#: given a malformed stem in testing the model correctly declined instead of inventing a meaning,
#: and a refusal is far cheaper to handle than a confident fabrication.
SYSTEM = (
    "You are a Sanskrit lexicographer. Given a Sanskrit word STEM, reply with its core meaning "
    "as 2-5 comma-separated English words or short phrases. No explanation, no grammar labels, "
    "no transliteration, no numbering. If the stem is a verbal root, give the action "
    "(e.g. 'to go, to move'). If you do not know the word, reply exactly: UNKNOWN"
)

#: Anything longer than this is the model explaining itself rather than glossing, and anything
#: containing these markers has drifted out of the requested format.
_MAX_CHARS = 120
_REFUSALS = ("unknown", "i do not", "i'm not", "as an ai", "sorry", "cannot")


def clean(reply: str) -> str | None:
    """The gloss, or None if the model declined or drifted out of format."""
    text = " ".join(reply.strip().split())
    if not text or len(text) > _MAX_CHARS:
        return None
    low = text.lower()
    if any(low.startswith(r) or low == r for r in _REFUSALS):
        return None
    text = text.strip(" .;:\"'")
    return text or None


def _load_cache() -> dict[str, str]:
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def generate(lemmas: list[str], sleep: float = 0.0) -> dict[str, str]:
    """Gloss each lemma, resuming from the on-disk cache so a long run can be interrupted."""
    from core.normalize import to_devanagari, to_iast
    from llm import chat

    cache = _load_cache()
    todo = [l for l in lemmas if l not in cache]
    print(f"  {len(lemmas):,} lemmas requested; {len(cache):,} cached; {len(todo):,} to generate")
    t0 = time.time()
    for i, lemma in enumerate(todo, 1):
        try:
            reply = chat(SYSTEM, f"Sanskrit stem: {to_iast(lemma)} ({to_devanagari(lemma)})")
        except Exception as exc:                       # noqa: BLE001 — one bad call must not end the run
            print(f"    {lemma}: {type(exc).__name__} {str(exc)[:50]}")
            continue
        gloss = clean(reply)
        cache[lemma] = gloss or ""                     # "" records "asked, no usable answer"
        if i % 100 == 0 or i == len(todo):
            rate = i / max(time.time() - t0, 1e-9)
            print(f"    {i:,}/{len(todo):,}  ({rate:.1f}/s)")
            _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if sleep:
            time.sleep(sleep)
    _CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def load_into_db(cache: dict[str, str] | None = None) -> int:
    from .dictionary import ensure_schema
    cache = cache if cache is not None else _load_cache()
    rows = [(lemma, SOURCE, gloss) for lemma, gloss in cache.items() if gloss]
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source = ?", (SOURCE,))
        conn.executemany("INSERT INTO sense (lemma, source, gloss) VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    print(f"  loaded {len(rows):,} LLM senses "
          f"({len(cache) - len(rows):,} lemmas returned nothing usable)")
    return len(rows)


def gita_lemmas() -> list[str]:
    """Distinct lemmas the engine resolves for the Gītā — the pilot's vocabulary."""
    from evals.sense_ranking import resolve
    from .ingest_gita import load
    seen: dict[str, None] = {}
    for verse in load():
        for word in verse.words:
            if not word:
                continue
            analysis = resolve(word)
            if analysis is not None:
                seen.setdefault(analysis.lemma.split("#")[0], None)
    return list(seen)


def all_lemmas() -> list[str]:
    conn = sqlite3.connect(_DB)
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT lemma FROM sense WHERE source != ?", (SOURCE,))]
    finally:
        conn.close()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "--gita"
    targets = all_lemmas() if which == "--all" else gita_lemmas()
    generate(targets)
    load_into_db()
