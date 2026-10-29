# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Import the Digital Corpus of Sanskrit as stage-level ground truth (Layer 2 of EVAL-STRATEGY).

DCS gives us what we cannot honestly write ourselves: 744,757 lines / 5.46M words of Sanskrit whose
analysis was verified by an annotator who is not us.  Twenty hand-made sentences cannot represent
Sanskrit, and annotations we author ourselves would only record our own opinion — the very thing
this project exists to guard against.

    Oliver Hellwig, Digital Corpus of Sanskrit (DCS), 2010-2021.  Licensed CC-BY 4.0.
    https://github.com/OliverHellwig/sanskrit

CoNLL-U maps onto our pipeline stages almost one-to-one:

    range line `18-19  tattvajñānāt`  ->  stage 2, segmentation (the fused surface form)
    LEMMA                             ->  stage 3, morphology
    FEATS `Case=Abl|Number=Sing`      ->  stage 3, morphology (cleaner than XPOS)
    MISC:Unsandhied                   ->  stage 2, the padapatha form

Two traps this handles, both of which would silently measure the WRONG THING:

  * `Case=Cpd` marks a compound (samasa) member, not a sandhi split.  `pramanaprameya...sthananam`
    is ONE 17-member compound, not 17 joined words.  Our segmenter splits sandhi; scoring it against
    compound decomposition would grade it on a task it does not perform.  Compound-internal members
    are therefore flagged and excluded from segmentation truth by default.
  * `UnsandhiedReconstructed=True` means the split was reconstructed, not hand-verified.  Kept, but
    flagged, so a gold set can be restricted to the verified subset.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path

from vidyut.lipi import Scheme, transliterate

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "dcs"
_REPO = "OliverHellwig/sanskrit"
_ROOT = "dcs/data/conllu/files"

#: A deliberately non-devotional spread — Sanskrit is mathematics, medicine, logic and drama too,
#: and an evaluation corpus drawn only from scripture would bake the opposite assumption in.
DEFAULT_TEXTS = [
    "Nyāyasūtra",          # logic
    "Carakasaṃhitā",       # medicine
    "Sūryasiddhānta",      # astronomy / mathematics
    "Arthaśāstra",         # statecraft, economics
    "Nāṭyaśāstra",         # drama, aesthetics
    "Kauṣītakyupaniṣad",   # philosophy
]


@dataclass
class Token:
    form: str                     # surface form, SLP1
    lemma: str                    # SLP1
    upos: str
    feats: dict[str, str]
    unsandhied: str | None        # padapatha form, SLP1
    in_compound: bool             # Case=Cpd -> a samasa member, NOT a sandhi split
    reconstructed: bool           # split inferred rather than hand-verified


@dataclass
class Sentence:
    sent_id: str
    text_iast: str
    text_slp1: str
    tokens: list[Token] = field(default_factory=list)
    #: (surface, [component words]) from CoNLL-U range lines — our stage-2 ground truth
    fusions: list[tuple[str, list[str]]] = field(default_factory=list)


def _slp1(text: str) -> str:
    return transliterate(text, Scheme.Iast, Scheme.Slp1)


def _gh(path: str) -> bytes:
    """Read one file from GitHub via `gh` (handles the repo's Devanagari-heavy filenames)."""
    quoted = urllib.parse.quote(path)
    out = subprocess.run(
        ["gh", "api", f"repos/{_REPO}/contents/{quoted}", "--jq", ".content"],
        capture_output=True, text=True, check=True,
    ).stdout
    return base64.b64decode(out)


def _list_chapters(text: str) -> list[str]:
    quoted = urllib.parse.quote(f"{_ROOT}/{text}")
    out = subprocess.run(
        ["gh", "api", f"repos/{_REPO}/contents/{quoted}", "--paginate", "--jq", ".[].path"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.splitlines() if p.endswith(".conllu")]


def parse_conllu(raw: str) -> list[Sentence]:
    """Parse CoNLL-U into Sentences, resolving multiword ranges into fusion ground truth."""
    sentences: list[Sentence] = []
    cur: Sentence | None = None
    pending: dict[tuple[int, int], str] = {}          # (start, end) -> fused surface form

    def flush() -> None:
        if cur is None:
            return
        for (start, end), surface in pending.items():
            # Group compound members back into single words before counting a split. A samasa runs
            # as Cpd, Cpd, ..., <final member carrying the case ending> — so the LAST member is not
            # marked Cpd, and testing `all(in_compound)` would wrongly read a 17-member compound as
            # 17 sandhi-joined words. Boundaries after a Cpd token are compound-internal; only the
            # others are true word boundaries, which is what our segmenter is asked to find.
            words: list[str] = []
            buf: list[str] = []
            for tok in cur.tokens[start - 1:end]:
                buf.append(tok.unsandhied or tok.form)
                if not tok.in_compound:
                    words.append("".join(buf))
                    buf = []
            if buf:
                words.append("".join(buf))
            if len(words) > 1:                       # a single word is not a sandhi split
                cur.fusions.append((surface, words))
        sentences.append(cur)

    for line in raw.splitlines():
        if line.startswith("# text = "):
            if cur is not None:
                flush()
            iast = line[len("# text = "):].strip()
            cur, pending = Sentence("", iast, _slp1(iast)), {}
            continue
        if line.startswith("# sent_id = ") and cur is not None:
            cur.sent_id = line[len("# sent_id = "):].strip()
            continue
        if not line or line.startswith("#") or cur is None:
            continue

        cols = line.split("\t")
        if len(cols) < 10:
            continue
        idx = cols[0]
        if "-" in idx:                                 # multiword range: the fused surface string
            a, b = idx.split("-")
            pending[(int(a), int(b))] = _slp1(cols[1])
            continue

        misc = dict(kv.split("=", 1) for kv in cols[9].split("|") if "=" in kv)
        feats = dict(kv.split("=", 1) for kv in cols[5].split("|") if "=" in kv)
        uns = misc.get("Unsandhied")
        cur.tokens.append(Token(
            form=_slp1(cols[1]),
            lemma=_slp1(cols[2]),
            upos=cols[3],
            feats=feats,
            unsandhied=_slp1(uns) if uns else None,
            in_compound=feats.get("Case") == "Cpd",
            reconstructed=misc.get("UnsandhiedReconstructed") == "True",
        ))
    flush()
    return sentences


def fetch(texts: list[str], max_chapters: int = 3) -> list[Sentence]:
    _CACHE.mkdir(exist_ok=True)
    out: list[Sentence] = []
    for name in texts:
        cache = _CACHE / f"{name}.conllu"
        if not cache.exists():
            try:
                chapters = _list_chapters(name)[:max_chapters]
            except subprocess.CalledProcessError:
                print(f"  {name}: NOT FOUND — skipping")
                continue
            cache.write_text("\n".join(_gh(p).decode("utf-8") for p in chapters), encoding="utf-8")
        sents = parse_conllu(cache.read_text(encoding="utf-8"))
        print(f"  {name}: {len(sents)} sentences")
        out += sents
    return out


def coverage(sents: list[Sentence]) -> None:
    """What fraction of DCS is actually usable as ground truth, per stage."""
    toks = [t for s in sents for t in s.tokens]
    if not toks:
        print("no tokens"); return
    n = len(toks)
    uns = sum(t.unsandhied is not None for t in toks)
    rec = sum(t.reconstructed for t in toks)
    cpd = sum(t.in_compound for t in toks)
    declined = sum("Case" in t.feats and t.feats["Case"] != "Cpd" for t in toks)
    fusions = [f for s in sents for f in s.fusions]

    print(f"\nDCS coverage — {len(sents)} sentences, {n} tokens\n" + "─" * 60)
    def row(label, k, note=""):
        print(f"  {label:34s} {100*k/n:5.1f}%  ({k:6d}/{n})  {note}")
    row("has Unsandhied (stage 2)", uns)
    row("  └─ hand-verified, not reconstructed", uns - rec, "← the trustworthy subset")
    row("compound member (Case=Cpd)", cpd, "← NOT sandhi; excluded")
    row("declined/inflected (stage 3)", declined, "← lemma+case+number truth")
    print(f"\n  sandhi fusions usable as split truth: {len(fusions)}"
          f"   (avg {sum(len(p) for _, p in fusions)/max(len(fusions),1):.1f} words each)")
    print("\n  examples:")
    for surface, parts in fusions[:6]:
        print(f"    {surface:32s} -> {' + '.join(parts)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Import DCS as stage-level ground truth")
    ap.add_argument("--texts", nargs="*", default=DEFAULT_TEXTS)
    ap.add_argument("--chapters", type=int, default=3, help="chapters per text")
    args = ap.parse_args()
    print("Fetching DCS (CC-BY 4.0, Oliver Hellwig 2010-2021):")
    coverage(fetch(args.texts, args.chapters))
