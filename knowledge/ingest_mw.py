# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Bulk-ingest Monier-Williams into the dictionary's `sense` table (source='MW').

Source: the Cologne Digital Sanskrit Dictionaries' Monier-Williams, as the ready-made
`lookup/mw.tsv` from github.com/tokushige-koyasan/cdsl-corpus — a processed form of
github.com/sanskrit-lexicon/MWS. Its `headword_slp1` column already matches our engine lemmas,
so no transliteration is needed; we only strip the Cologne body markup.

Data © the Cologne Digital Sanskrit Dictionaries; digitization layer CC-BY-SA-4.0; the MW text
itself is public domain. Attribute Cologne + sanskrit-lexicon/MWS.

    python -m knowledge.ingest_mw          # download (cached) + load all of MW
"""
from __future__ import annotations

import html
import re
import sqlite3
import urllib.request
from pathlib import Path

from .dictionary import _DB, ensure_schema

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "mw.tsv"
_URL = "https://raw.githubusercontent.com/tokushige-koyasan/cdsl-corpus/main/lookup/mw.tsv"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_GLOSS_CAP = 600  # keep display sane


def _clean(body: str) -> str:
    """Cologne body markup → readable gloss: drop tags (keep inner text), unescape, tidy."""
    t = _TAG.sub("", body).replace("¦", " ")
    t = html.unescape(t)
    t = _WS.sub(" ", t).strip().strip('"').strip()
    return t


def _download() -> None:
    if _CACHE.exists() and _CACHE.stat().st_size > 1_000_000:
        return
    print(f"downloading MW (~44 MB) → {_CACHE.name} ...")
    urllib.request.urlretrieve(_URL, _CACHE)


def ingest(limit: int | None = None) -> int:
    """Load MW into `sense` (source='MW'), one row per dictionary entry. Returns row count."""
    _download()
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source = 'MW'")

        rows: list[tuple[str, str, str]] = []
        cur_key = cur_lemma = None
        buf: list[str] = []
        n_entries = 0

        def flush():
            if cur_lemma and buf:
                gloss = _clean(" ".join(buf))[:_GLOSS_CAP]
                if len(gloss) >= 2:
                    rows.append((cur_lemma, "MW", gloss))

        with _CACHE.open(encoding="utf-8") as f:
            f.readline()  # header
            for line in f:
                parts = line.rstrip("\n").split("\t", 4)
                if len(parts) < 5:
                    continue
                _iast, slp1, entry_id, _page, body = parts
                key = (slp1, entry_id.split(".")[0])  # group main entry + its continuation lines
                if key != cur_key:
                    flush()
                    if limit and n_entries >= limit:
                        break
                    cur_key, cur_lemma, buf = key, slp1, []
                    n_entries += 1
                buf.append(body)
            else:
                flush()

        conn.executemany("INSERT INTO sense (lemma, source, gloss) VALUES (?, ?, ?)", rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"ingested {ingest():,} Monier-Williams entries")
