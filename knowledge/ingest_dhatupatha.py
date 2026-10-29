# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""The Dhātupāṭha — Pāṇini's own list of verbal roots and what they mean.

    python -m knowledge.ingest_dhatupatha

The root list that accompanies the Aṣṭādhyāyī: ~2,200 dhātus, each with its gaṇa (conjugation
class) and an **artha** stating its sense — `BU` is *sattāyām*, "in the sense of existence". This is
the most authoritative statement of a root's meaning there is, and it has been sitting in
`vidyut-data/` all along, referenced in exactly one line of our code as a boolean.

Verbs are where this matters most. A verb anchors the kāraka graph, and Monier-Williams' verb
entries are its messiest — pages of conjugation tables around the definition, which is why 1,260 of
them were being discarded outright until today.

Vidyut expands the list across prefixes, giving 45k entries: `praBU`, `saMBU`, `samudBU` beside
`BU`. That is a real gain, because MW often has no usable entry for a prefixed root at all. But it
comes with a caveat kept in the ranking below: **the artha is the base root's**, so `parABU` is
listed "to exist" when it in fact means "to perish". Apte and Macdonell record the prefixed sense
properly, so they outrank this source; the Dhātupāṭha sits above MW, not above them.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from .dictionary import ensure_schema

_DB = Path(__file__).resolve().parent / "sanskrit.db"
_GLOSS_CAP = 300


#: A base root carries Pāṇini's own artha and is the authority on its own meaning. A prefixed form
#: does NOT: Vidyut inherits the base artha across prefixes, so `parābhū` is labelled *sattāyām*
#: ("existence") when the word means "to perish". Separating them lets the first outrank every
#: dictionary — which is right, since the lexicographers are downstream of the Dhātupāṭha — while
#: the second defers to a dictionary that actually recorded the prefixed sense.
BASE = "dhatupatha"
PREFIXED = "dhatupatha-upasarga"


def entries() -> list[tuple[str, str, str]]:
    """(root, source, gloss). The Sanskrit artha travels with the English, because the
    artha-nirdeśa is the authority and the English is a rendering of it."""
    from core.morphology import kosha

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for entry in kosha().dhatus():
        root = (entry.clean_text or "").strip()
        english = (entry.artha_en or "").strip()
        if not root or not english:
            continue
        sanskrit = (entry.artha_sa or "").strip()
        gana = str(getattr(entry.dhatu, "gana", "") or "")
        detail = ", ".join(x for x in (sanskrit, gana) if x)
        gloss = f"{english} (√{root}, {detail})" if detail else english
        key = (root, gloss)
        if key in seen:
            continue
        seen.add(key)
        prefixed = bool(list(getattr(entry.dhatu, "prefixes", []) or []))
        out.append((root, PREFIXED if prefixed else BASE, gloss[:_GLOSS_CAP]))
    return out


def ingest() -> int:
    rows = list(entries())
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source IN (?, ?)", (BASE, PREFIXED))
        conn.executemany("INSERT INTO sense (lemma, source, gloss) VALUES (?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    print(f"ingested {ingest():,} Dhātupāṭha root senses")
