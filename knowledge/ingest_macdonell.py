# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Macdonell's *Practical Sanskrit Dictionary* — the most concise of the three.

    python -m knowledge.ingest_macdonell

The third independent lexicon, and the one written for students construing a line. Where MW gives
`hasta` an encyclopaedia and Apte gives it four numbered senses, Macdonell gives "hand (ord. mg.)"
and then the specialised readings.

Two conveniences over Apte: its headwords are already **bare stems** (`Darma`, `hasta`), so they
meet our lemmas with no stemming; and the accented citation form is reliably followed by a `<lex>`
part-of-speech tag, which marks exactly where the definition begins.

Kept as `source='macdonell'`, separate from MW and Apte. Three lexicons agreeing on a word is a
confidence signal worth having; merging them destroys it.
"""
from __future__ import annotations

import csv
import html
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

from .dictionary import ensure_schema
from .ingest_mw import clean_for_reading
from .quality import Reconciler, classify_rejection

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "md.tsv"
_DB = _HERE / "sanskrit.db"
_URL = "https://raw.githubusercontent.com/tokushige-koyasan/cdsl-corpus/main/lookup/md.tsv"
_GLOSS_CAP = 400

#: The definition begins after the part-of-speech tag; before it sits the accented citation form
#: (`dhár-ma,`), which is the headword again and not a meaning.
_AFTER_LEX = re.compile(r"^.*?<lex>.*?</lex>\s*", re.S)
_HEADWORD = re.compile(r"^\s*\{#.*?#\}\s*¦?\s*", re.S)
_SANSKRIT = re.compile(r"\{#.*?#\}", re.S)
_ITALIC = re.compile(r"\{%(.*?)%\}", re.S)          # notes like "often personified" — keep the text
_NUMBER = re.compile(r"¤.*?¤", re.S)
_BULLET = re.compile(r"🞄")                          # a typesetting line-break mark, not punctuation
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(body: str) -> str:
    text = _HEADWORD.sub("", body)
    text = _AFTER_LEX.sub("", text) if "<lex>" in text else text
    text = _BULLET.sub(" ", text)
    text = _NUMBER.sub(" ", text)
    text = _SANSKRIT.sub(" ", text)
    text = _ITALIC.sub(r"\1", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = re.sub(r"\s*([;,:])\s*(?:[;,:]\s*)+", r"\1 ", text)
    return text.strip().strip('"').strip(" ;,:-")



#: A gloss must be longer than three characters OR be a plain word. The bare length bar was
#: deleting real one-word senses — "Sky", "Oil", "Sin", "Dew", "Tin" — while its actual targets
#: are apparatus fragments that are never purely alphabetic: "a.", "P.", "{ }", "=". Measured on
#: Apte: 8,395 fragments fall under the bar, 8,065 of them apparatus and ~30 real words.
#: "See" is excluded by name because it is a cross-reference, not a meaning.
_XREF_WORDS = frozenset({"see", "cf", "id", "do", "ib", "or", "and", "as", "if", "a"})


def _is_real_gloss(gloss: str) -> bool:
    g = gloss.strip()
    if len(g) > 3:
        return True
    return g.isalpha() and len(g) >= 2 and g.lower() not in _XREF_WORDS

def senses(body: str, rec=None, lemma: str | None = None) -> list[str]:
    """Macdonell separates senses with semicolons; each becomes its own row."""
    cleaned = _clean(body)
    out: list[str] = []
    for part in cleaned.split(";"):
        raw = part.strip()
        if rec is not None:
            rec.seen()
        gloss = clean_for_reading(raw)
        if gloss and _is_real_gloss(gloss):
            out.append(gloss[:_GLOSS_CAP])
            if rec is not None:
                rec.kept()
        elif rec is not None:
            rec.reject(raw or part, classify_rejection(raw, gloss or ""), lemma)
    return out


def _download() -> None:
    if _CACHE.exists() and _CACHE.stat().st_size > 1_000_000:
        return
    print(f"downloading Macdonell (~6 MB) → {_CACHE.name} ...")
    urllib.request.urlretrieve(_URL, _CACHE)


def ingest(limit: int | None = None) -> int:
    _download()
    csv.field_size_limit(10**7)
    rec = Reconciler("macdonell")
    rows: list[tuple[str, str, str]] = []
    with _CACHE.open(encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh, delimiter="\t")):
            if limit and n >= limit:
                break
            lemma = row["headword_slp1"]                 # already a bare stem
            for gloss in senses(row["body"], rec, lemma):
                rows.append((lemma, "macdonell", gloss))

    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        rec.check()
        conn.execute("DELETE FROM sense WHERE source = 'macdonell'")
        conn.executemany("INSERT INTO sense (lemma, source, gloss) VALUES (?, ?, ?)", rows)
        rec.record(conn, origin=_URL, path=_CACHE)
        print("  " + rec.summary())
        conn.commit()
    finally:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    n = ingest(int(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"ingested {n:,} Macdonell senses")
