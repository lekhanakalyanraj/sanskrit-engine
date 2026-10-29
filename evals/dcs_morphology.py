# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 3 at scale — morphology measured against DCS lemma + FEATS.

    python -m evals.dcs_morphology

Measured in ISOLATION from stage 2: the input is DCS's own `Unsandhied` (padapatha) form, not our
segmenter's output. Feeding our segmentation in would fold stage-2 errors into a stage-3 number and
we would not be able to tell which link had failed — the exact defect this whole eval layer exists
to remove.

What this measured (see EVAL-STRATEGY.md for the figures): the **lexicon is not the bottleneck** —
oracle sits at ~95% and not one token was unanalysable. The gap is entirely in selection, and for
gender there is no selection to speak of: `disambiguate.select` reasons about CASE only, then takes
the first candidate matching pos+case, so gender falls out of candidate ORDER. `sTAnAnAm` offers
feminine/masculine/neuter under one lemma and we take index 0. That is arbitrary rather than wrong-
headed, and it is cheap to fix, because a Sanskrit nominal stem carries an inherent gender that the
lemma already determines.

Two numbers are reported for every field, and the gap between them is the point:

  * **oracle**   — the correct analysis is somewhere in the candidate list (a lexicon question)
  * **selected** — `disambiguate.select` actually picked it (a ranking question)

Segmentation showed the same shape: on all four verses we track as failures the right answer was
already among the candidates and the ranker chose wrong. If that repeats here, the bottleneck is
ranking across the board, and ranking is exactly what cannot be checked without recorded truth.

Measurement artifacts handled, each of which would otherwise be scored as a morphology error:

  * DCS records the WRITTEN form (`aDigamaH`); the kosha is keyed on the pre-visarga pada
    (`aDigamas`), so input goes through `_underlying` first. Skipping this measures visarga.
  * `Case=Cpd` members are samasa constituents with no independent case — excluded.
  * Our POS tagset is coarse (noun/verb/particle/unknown) against DCS's eight UD tags. Reported
    separately under a stated mapping rather than folded into an accuracy figure it would distort.
"""
from __future__ import annotations

import collections

from core.disambiguate import select
from core.morphology import analyze_candidates
from core.segment import _underlying
from knowledge.ingest_dcs import DEFAULT_TEXTS, fetch

CASE = {"Nom": "nominative", "Acc": "accusative", "Ins": "instrumental", "Dat": "dative",
        "Abl": "ablative", "Gen": "genitive", "Loc": "locative", "Voc": "vocative"}
GENDER = {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter"}
NUMBER = {"Sing": "singular", "Dual": "dual", "Plur": "plural"}
#: DCS UD tag -> our coarse tag. Sanskrit adjectives/numerals decline as nouns do, so collapsing
#: them is defensible; pronouns are ambiguous for us (many sit in the closed-class PARTICLES set).
UPOS = {"NOUN": "noun", "ADJ": "noun", "NUM": "noun", "VERB": "verb",
        "PART": "particle", "CONJ": "particle", "ADV": "particle"}

FIELDS = [("lemma", None), ("case", CASE), ("gender", GENDER), ("number", NUMBER)]


def _lemma(a) -> str:
    return (a.lemma or "").split("#")[0]


def report(texts: list[str] | None = None, verified_only: bool = False) -> None:
    sents = fetch(texts or DEFAULT_TEXTS)
    oracle: collections.Counter = collections.Counter()
    picked: collections.Counter = collections.Counter()
    total: collections.Counter = collections.Counter()
    pos_confusion: collections.Counter = collections.Counter()
    no_candidates = 0
    misses: list[str] = []

    for sent in sents:
        toks = [t for t in sent.tokens
                if t.unsandhied and not t.in_compound and not (verified_only and t.reconstructed)]
        if not toks:
            continue
        forms = [_underlying(t.unsandhied) or t.unsandhied for t in toks]
        cand_lists = [analyze_candidates(f) for f in forms]
        chosen = select(cand_lists)

        for tok, cands, sel in zip(toks, cand_lists, chosen):
            if not cands:
                no_candidates += 1
                continue
            for field, mapping in FIELDS:
                if field == "lemma":
                    want = tok.lemma
                else:
                    raw = tok.feats.get(field.capitalize())
                    if raw is None or raw not in (mapping or {}):
                        continue
                    want = mapping[raw]
                total[field] += 1
                got = _lemma(sel) if field == "lemma" else (sel.features.get(field) if sel else None)
                cand_vals = ({_lemma(c) for c in cands} if field == "lemma"
                             else {c.features.get(field) for c in cands})
                picked[field] += (got == want)
                oracle[field] += (want in cand_vals)
                if field == "lemma" and got != want and len(misses) < 8:
                    misses.append(f"{tok.unsandhied:18s} want={want:14s} got={got}")
            if sel and tok.upos in UPOS:
                pos_confusion[(tok.upos, sel.pos)] += 1

    label = "hand-verified only" if verified_only else "all tokens"
    print(f"\nStage 3 (morphology) vs DCS — {label}\n" + "─" * 66)
    print(f"  {'field':10s} {'selected':>10s} {'oracle':>10s} {'gap':>8s}   n")
    for field, _ in FIELDS:
        n = total[field]
        if not n:
            continue
        s, o = 100 * picked[field] / n, 100 * oracle[field] / n
        print(f"  {field:10s} {s:9.1f}% {o:9.1f}% {o - s:7.1f}pt   {n}")
    print(f"\n  tokens the kosha could not analyse at all: {no_candidates}")
    print("\n  coarse POS (our 4 tags vs DCS's 8 — mapping is lossy, read with care):")
    for (dcs, ours), k in pos_confusion.most_common(6):
        mark = "✓" if UPOS.get(dcs) == ours else "✗"
        print(f"    {mark} DCS {dcs:5s} -> ours {ours:9s} {k}")
    print("\n  sample lemma misses:")
    for m in misses[:6]:
        print(f"    {m}")


if __name__ == "__main__":
    report()
    report(verified_only=True)
