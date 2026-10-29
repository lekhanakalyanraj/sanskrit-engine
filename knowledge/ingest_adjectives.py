# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Which nominals the lexicographers record as qualificative (`mfn.` / `a.`).

    python -m knowledge.ingest_adjectives

Pāṇinian grammar has no adjective part-of-speech: there are subanta and tiṅanta, and what English
calls an adjective is a nominal standing in a **viśeṣaṇa relation**. The tradition distinguishes it
semantically — *guṇa-vācaka* (quality-denoting) qualifies *dravya-vācaka* (substance-denoting) —
never by form, which is why every morphological signal tried for it failed:

    declared lingas       ADJ 56.1%  NOUN 14.3%   +41.8
    derived (kṛdanta)     ADJ 40.3%  NOUN 49.5%    −9.2   (Sanskrit derives nouns too)
    **lexicographers' mark**  ADJ 96.1%  NOUN 38.1%   **+57.9**

When Monier-Williams writes `mfn.`, he is recording precisely that judgment word by word: this
nominal takes the gender of what it qualifies rather than owning one. That is the distinction the
grammar defines and the dictionaries preserve — not a heuristic to be rediscovered from statistics.

The 38% on nouns is not noise: many Sanskrit nominals really are used both ways, so this is a
FILTER on candidates, not a classifier.
"""
from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DB = _HERE / "sanskrit.db"

#: Each dictionary marks it in its own notation, all three near the head of the entry.
_SOURCES = (
    ("mw.tsv",   re.compile(r"<lex>\s*(?:mfn|mf\([^)]*\)n)\s*\.", re.I), None, False),
    ("ap90.tsv", re.compile(r"<ab>\s*a\.\s*</ab>"),                220,  True),
    ("md.tsv",   re.compile(r"<lex>\s*a\.\s*</lex>"),              220,  False),
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS adjective (lemma TEXT PRIMARY KEY)")


def lemmas() -> set[str]:
    found: set[str] = set()
    csv.field_size_limit(10**7)
    for name, pattern, head_chars, stem in _SOURCES:
        path = _HERE / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                body = row["body"][:head_chars] if head_chars else row["body"]
                if not pattern.search(body):
                    continue
                key = row["headword_slp1"]
                # Apte cites the nominative singular; our lemmas are bare stems
                if stem and key.endswith(("H", "M")):
                    key = key[:-1]
                found.add(key)
    return found


def ingest() -> int:
    rows = [(l,) for l in sorted(lemmas())]
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM adjective")
        conn.executemany("INSERT OR IGNORE INTO adjective (lemma) VALUES (?)", rows)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    print(f"marked {ingest():,} lemmas as qualificative")
