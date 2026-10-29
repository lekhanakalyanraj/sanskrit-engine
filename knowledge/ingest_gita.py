# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""The Bhagavadgītā — 701 verses with a word-by-word split (gita/gita, CC).

    python -m knowledge.ingest_gita

Why this matters more than another corpus: **every accuracy figure in this project is measured on
Nyāya, Caraka and Sūryasiddhānta prose**, because that is what carries published annotation. The
Gītā is one of the texts the engine actually exists to read, and it is not in DCS — the Mahābhārata
files there stop short of book 6. So until now we have had no idea whether any of our numbers
describe the target material.

The `word_meanings` field gives a padapāṭha — the verse split into words, each with a gloss — which
is ground truth for segmentation. Two caveats kept in view:

  * the romanisation is **not IAST**: `kṣhetre`, `phaleṣhu`, `kadāchana` insert an `h` that IAST
    does not, so it must be normalised before anything can be compared;
  * the glosses are **interpretive, not lexical** — `karmaṇi` is rendered "in prescribed duties"
    rather than "in action". Fine for sanity-checking a reading; wrong to score a dictionary against.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from core.normalize import to_slp1

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "gita_verse.json"
_URL = "https://raw.githubusercontent.com/gita/gita/main/data/verse.json"

#: Their scheme → IAST. Order matters: the digraph must go before the letter it contains.
_ROMAN_FIXES = [("chh", "ch"), ("kṣh", "kṣ"), ("ṣh", "ṣ"), ("śh", "ś"), ("ch", "c")]
_VERSE_MARK = re.compile(r"[।॥]+\s*[\d.]*\s*")
_PAREN = re.compile(r"\([^)]*\)")


@dataclass
class Verse:
    chapter: int
    number: int
    devanagari: str
    words: list[str] = field(default_factory=list)      # SLP1, from the padapāṭha
    glosses: list[str] = field(default_factory=list)    # English, interpretive


def _to_iast(text: str) -> str:
    out = text
    for wrong, right in _ROMAN_FIXES:
        out = out.replace(wrong, right)
    return out


def _split_word_meanings(raw: str) -> tuple[list[str], list[str]]:
    """`karmaṇi—in prescribed duties; eva—only; …` → parallel word and gloss lists."""
    words: list[str] = []
    glosses: list[str] = []
    for chunk in re.split(r"[;|]", raw or ""):
        if "—" not in chunk:
            continue
        head, _, gloss = chunk.partition("—")
        head = _PAREN.sub("", head).strip().strip("-").strip()
        if not head:
            continue
        # a hyphen marks a compound in this source; keep it as one word, as the engine does
        words.append(to_slp1(_to_iast(head.replace("-", ""))))
        glosses.append(gloss.strip())
    return words, glosses


def _download() -> None:
    if _CACHE.exists() and _CACHE.stat().st_size > 100_000:
        return
    print(f"downloading the Gītā → {_CACHE.name} ...")
    urllib.request.urlretrieve(_URL, _CACHE)


def load() -> list[Verse]:
    _download()
    out: list[Verse] = []
    for row in json.loads(_CACHE.read_text(encoding="utf-8")):
        dev = _VERSE_MARK.sub(" ", row.get("text", "")).replace("\n", " ").strip()
        words, glosses = _split_word_meanings(row.get("word_meanings", ""))
        out.append(Verse(row["chapter_number"], row["verse_number"], dev, words, glosses))
    return out


if __name__ == "__main__":
    verses = load()
    words = sum(len(v.words) for v in verses)
    print(f"loaded {len(verses)} verses, {words:,} word tokens with glosses")
    v = next(x for x in verses if (x.chapter, x.number) == (2, 47))
    print(f"\nBG 2.47")
    print(f"  {v.devanagari[:70]}")
    for w, g in list(zip(v.words, v.glosses))[:6]:
        print(f"    {w:14s} {g}")
