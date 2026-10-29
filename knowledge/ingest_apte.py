# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Apte's *Practical Sanskrit-English Dictionary* — the reader's lexicon.

    python -m knowledge.ingest_apte

Monier-Williams is an encyclopaedic scholarly reference: it answers "everything known about this
word", which is why its entries carry etymologies, Vedic citations, and asides about Rāvaṇa's
brothers. Apte answers a different question — "what does this word mean in the line I am reading" —
and most of what we spent days stripping out of MW simply is not in it.

Two structural gifts:

  * **Senses are explicitly numbered** (`{@1@}`, `{@--2@}`), so each becomes its own row instead of
    one blob that has to be re-split later.
  * **Headwords are cited in the nominative singular** (`DarmaH`, `anuyAtraM`) where our lemmas are
    bare stems, so the key needs stemming — after which 25,855 of them meet our MW lemmas and 73%
    of the 2,000 commonest words in real text are covered.

Stored under `source='apte'`, never merged with MW. Two independent lexicons agreeing is a
confidence signal; one overwriting the other destroys it.
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
_CACHE = _HERE / "ap90.tsv"
_DB = _HERE / "sanskrit.db"
_URL = "https://raw.githubusercontent.com/tokushige-koyasan/cdsl-corpus/main/lookup/ap90.tsv"
_GLOSS_CAP = 400

_SENSE_SPLIT = re.compile(r"\{@\s*-*\s*\d+\s*@\}")      # {@1@} · {@--2@}
_SANSKRIT = re.compile(r"\{#.*?#\}", re.S)              # Sanskrit headwords, etymologies, quotes
_EMPH = re.compile(r"\{%(.*?)%\}", re.S)                # emphasis — keep the text
_CITATION = re.compile(r"<ls>.*?</ls>", re.S)           # Ś. 5. 4 — provenance, not meaning
_LBINFO = re.compile(r"<lbinfo[^>]*/>")                 # typesetting hyphenation artefacts
_ETYM = re.compile(r"\[[^\[\]]*\]")                     # the leading etymology bracket
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    text = _CITATION.sub(" ", text)
    text = _LBINFO.sub(" ", text)
    text = _SANSKRIT.sub(" ", text)
    text = _EMPH.sub(r"\1", text)
    text = _ETYM.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text).replace("¦", " ")
    text = _WS.sub(" ", text)
    # Removing Sanskrit quotes and citations leaves their punctuation behind — "Food;;; I am your
    # prey". Collapse the runs rather than shipping them to a reader.
    text = re.sub(r"\s*([;,:])\s*(?:[;,:]\s*)+", r"\1 ", text)
    text = re.sub(r"^\s*[;,:.\s]+", "", text)
    return text.strip().strip('"').strip(" ;,:-")


def stem(headword: str) -> str:
    """Apte cites the nominative singular; our lemmas are bare stems.

    `DarmaH` → `Darma`, `anuyAtraM` → `anuyAtra`, `muniH` → `muni`. Without this the two lexicons
    never meet, because every Apte key carries an ending our lemmas do not.
    """
    return headword[:-1] if headword.endswith(("H", "M")) else headword



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
    """One gloss per numbered sense, cleaned. Apte numbers them, so we need not guess boundaries.

    `rec` is an optional Reconciler: every fragment that does NOT survive is quarantined with a
    reason rather than vanishing, so a cleaning change that eats real meaning shows up as a
    reject-count spike instead of a silently smaller table.
    """
    out: list[str] = []
    for part in _SENSE_SPLIT.split(body):
        raw = _clean(part)
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
    print(f"downloading Apte (~11 MB) → {_CACHE.name} ...")
    urllib.request.urlretrieve(_URL, _CACHE)


def ingest(limit: int | None = None) -> int:
    _download()
    csv.field_size_limit(10**7)
    # Apte's markup splits one entry into many fragments, a large share of which are pure
    # apparatus ("a.", "P.", "{ }") rather than senses, so its legitimate quarantine rate is
    # structurally higher than MW's or Macdonell's. Inspected, not guessed: of 8,395 sub-bar
    # fragments, 8,065 were apparatus. The ceiling still catches a cleaner that starts eating
    # meaning — the bad abbreviation regex pushed this past 25%.
    rec = Reconciler("apte", max_loss=0.22)
    rows: list[tuple[str, str, str]] = []
    with _CACHE.open(encoding="utf-8") as fh:
        for n, row in enumerate(csv.DictReader(fh, delimiter="\t")):
            if limit and n >= limit:
                break
            lemma = stem(row["headword_slp1"])
            for gloss in senses(row["body"], rec, lemma):
                rows.append((lemma, "apte", gloss))

    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        rec.check()                      # refuses to commit an unexplained delta
        conn.execute("DELETE FROM sense WHERE source = 'apte'")
        conn.executemany("INSERT INTO sense (lemma, source, gloss) VALUES (?, ?, ?)", rows)
        rec.record(conn, origin=_URL, path=_CACHE)
        conn.commit()
        print("  " + rec.summary())
    finally:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    n = ingest(int(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"ingested {n:,} Apte senses")
