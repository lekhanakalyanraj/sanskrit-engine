# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 3 (symbolic) — dictionary lookup: lemma → English sense(s).

The deterministic *symbolic* half of retrieval: exact lookup by lemma, no ML. Backed by SQLite
(the architecture's symbolic store; Postgres later at scale). Seeded from dictionary.yaml now;
bulk Monier-Williams loads into the same `sense` table (see README) with source="MW".

    from knowledge.dictionary import lookup, attach_senses
    lookup("jala")            # [Sense(source="seed", gloss="water")]
    attach_senses(parse)      # fills each token.senses in a ParseResult
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml

from core.models import ParseResult, Sense

_HERE = Path(__file__).resolve().parent
_SEED = _HERE / "dictionary.yaml"
_DB = _HERE / "sanskrit.db"

_HOMONYM = re.compile(r"#\d+$")  # lexicon marks homonyms as e.g. 'pA#1'


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS sense (lemma TEXT NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sense_lemma ON sense (lemma)")


def build_db() -> None:
    """(Re)load the seed lexicon (source='seed'). Leaves other sources (e.g. 'MW') intact."""
    entries = yaml.safe_load(_SEED.read_text(encoding="utf-8")) or {}
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source = 'seed'")
        conn.executemany(
            "INSERT INTO sense (lemma, source, gloss) VALUES (?, 'seed', ?)",
            list(entries.items()),
        )
        conn.commit()
    finally:
        conn.close()


def _conn() -> sqlite3.Connection:
    if not _DB.exists():
        build_db()
    return sqlite3.connect(_DB)


def lookup(lemma: str) -> list[Sense]:
    """Senses for a lemma (SLP1). Homonym markers are stripped before lookup."""
    lemma = _HOMONYM.sub("", lemma)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT source, gloss FROM sense WHERE lemma = ? ORDER BY (source != 'seed'), source",
            (lemma,),
        ).fetchall()
    finally:
        conn.close()
    return [Sense(source=s, gloss=g) for s, g in rows]


def attach_senses(result: ParseResult) -> ParseResult:
    """Fill each token's `.senses` from the dictionary (mutates and returns the result)."""
    for token in result.tokens:
        if token.analysis is not None:
            token.senses = lookup(token.analysis.lemma)
    return result


if __name__ == "__main__":
    build_db()
    for w in ("jala", "SUnya", "Atman", "gam"):
        print(f"{w}: {[s.gloss for s in lookup(w)]}")
