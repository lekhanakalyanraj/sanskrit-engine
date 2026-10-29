# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""The Hyderabad kāraka gold corpus — Pāṇinian dependency annotation.

    python -m knowledge.ingest_uohyd

3,736 sentences, 20,661 tokens, annotated with the SAME relation vocabulary this engine uses:
kartā, karma, karaṇa, apādāna, adhikaraṇa, sambandha, viśeṣaṇa. From the Sanskrit Consortium
project at the University of Hyderabad (Kulkarni et al.), released under the licence in the archive.

Why it matters more than another corpus: DCS carries morphology in abundance but its dependency
layer is tiny — 449 tokens in our slice, and **8 adjective links**. Agreement between an adjective
and its noun is the strongest Pāṇinian constraint available, and it was effectively unmeasurable.
Here there are **2,602 viśeṣaṇa links**.

Format is `SENT:` then numbered `index word relation head` lines, in WX notation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate


def _wx(text: str) -> str:
    """WX → SLP1, stated rather than detected.

    The two schemes share letters and disagree on them: `w` is *t* in WX and *ṭ* in SLP1, `X` is
    *dh* against *ḹ*. Auto-detection cannot separate them — our own SLP1 marker set (z f F x X) is
    satisfied by WX text — so a corpus documented as WX must say so. Left to the detector,
    `wIre` ("on the bank") came through as *ṭīre*.
    """
    return transliterate(text, sanscript.WX, sanscript.SLP1)

_DIR = Path(__file__).resolve().parent / "uohyd" / "Dependency_analysis"

#: Hyderabad's relation names → ours. Their scheme is finer; several of theirs are subtypes of one
#: kāraka (kāla- and deśa-adhikaraṇa are both adhikaraṇa), so the mapping folds rather than renames.
RELATION = {
    "karwA": "kartā", "karma": "karma", "karaNam": "karaṇa",
    "sampraxAnam": "sampradāna", "apAxAnam": "apādāna",
    "aXikaraNam": "adhikaraṇa", "kAlAXikaraNam": "adhikaraṇa", "xeSAXikaraNam": "adhikaraṇa",
    "sambanXaH": "sambandha", "RaRTIsambanXaH": "sambandha",
    "viSeRaNam": "viśeṣaṇa",
}


@dataclass
class Token:
    index: int
    word: str                 # SLP1
    relation: str | None      # our vocabulary, or None when unmapped
    raw_relation: str
    head: int | None


@dataclass
class Sentence:
    text: str = ""            # SLP1
    tokens: list[Token] = field(default_factory=list)

    def links(self, relation: str) -> list[tuple[Token, Token]]:
        """(dependent, head) pairs for one relation — the structure oracle we lacked."""
        by_index = {t.index: t for t in self.tokens}
        return [(t, by_index[t.head]) for t in self.tokens
                if t.relation == relation and t.head in by_index]


_ROW = re.compile(r"^(\d+)\s+(\S+)(?:\s+(\S+))?(?:\s+(\d+))?\s*$")


def load() -> list[Sentence]:
    out: list[Sentence] = []
    for path in sorted(_DIR.glob("*.txt")):
        current: Sentence | None = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("SENT:"):
                if current and current.tokens:
                    out.append(current)
                current = Sentence(text=_wx(line[5:].strip()))
                continue
            if not line or line.startswith("ANALYSIS") or current is None:
                continue
            m = _ROW.match(line)
            if not m:
                continue
            idx, word, rel, head = m.groups()
            # a bare `(aswi)` marks an elided copula the annotators supplied; keep the token but
            # strip the brackets so it transliterates
            word = word.strip("()?।.,")
            if not word:
                continue
            current.tokens.append(Token(
                index=int(idx), word=_wx(word),
                relation=RELATION.get(rel or ""), raw_relation=rel or "",
                head=int(head) if head else None,
            ))
        if current and current.tokens:
            out.append(current)
    return out


if __name__ == "__main__":
    sents = load()
    toks = sum(len(s.tokens) for s in sents)
    vis = sum(len(s.links("viśeṣaṇa")) for s in sents)
    kar = sum(len(s.links("kartā")) for s in sents)
    print(f"loaded {len(sents):,} sentences, {toks:,} tokens")
    print(f"  viśeṣaṇa links: {vis:,}   kartā links: {kar:,}")
    s = next(x for x in sents if x.links("viśeṣaṇa"))
    print(f"\n  {s.text[:64]}")
    for dep, head in s.links("viśeṣaṇa")[:3]:
        print(f"    {dep.word:22s} viśeṣaṇa→ {head.word}")
