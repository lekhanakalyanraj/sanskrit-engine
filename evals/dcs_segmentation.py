# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 2 at scale — segmentation measured against DCS, ground truth we did not author.

    python -m evals.dcs_segmentation

Our 20 hand-made gold sentences score 100% at every stage, which tells us nothing: they contain no
genuine ambiguity, so nothing is selected and nothing is measured. This scores the segmenter on
real sandhi fusions annotated by someone else.

**Only fusions with trustworthy expectations are scored.** DCS records a compound's members
separately, and reconstructing the compound by joining them with "" produces strings that are not
Sanskrit — `ukta` + `aDyavasAyAt` never surfaces as `uktaaDyavasAyAt`, because internal sandhi
applies. Scoring against those fabricated targets understated segmentation by **11 points** (52.6%
against 63.6%) and, worse, made half of all errors look like missing lexicon when they were the
measurement's own invention. A fusion is scored only when every expected part is an actual DCS
token; the rest are counted and reported, never graded.

The other artifact kept separate is **visarga representation**: DCS writes a pada's final visarga
`H`, our kosha-facing form ends in `s`. That is `core.normalize.to_pausa`'s job, not a segmentation
error, so both sides are compared in the written form.
"""
from __future__ import annotations

import collections

from core.normalize import to_pausa
from core.segment import segment
from knowledge.ingest_dcs import DEFAULT_TEXTS, Sentence, fetch


def _scoreable(sent: Sentence) -> list[tuple[str, list[str]]]:
    """Fusions whose every expected part is a real DCS token, not a compound reconstruction."""
    real = {t.unsandhied for t in sent.tokens if t.unsandhied}
    return [(surface, parts) for surface, parts in sent.fusions if all(p in real for p in parts)]


def _written(words: list[str]) -> list[str]:
    return [to_pausa(w) for w in words]


def report(texts: list[str] | None = None) -> float:
    sents = fetch(texts or DEFAULT_TEXTS)
    cases = [c for s in sents for c in _scoreable(s)]
    skipped = sum(len(s.fusions) for s in sents) - len(cases)
    if not cases:
        print("no scoreable fusions — run `python -m knowledge.ingest_dcs` first")
        return 0.0

    exact = 0
    shape: collections.Counter = collections.Counter()
    by_size: collections.Counter = collections.Counter()
    ok_by_size: collections.Counter = collections.Counter()
    misses: list[tuple[str, list[str], list[str]]] = []

    for surface, want in cases:
        got = segment(surface)
        by_size[len(want)] += 1
        if _written(got) == _written(want):
            exact += 1
            ok_by_size[len(want)] += 1
        else:
            shape["under-split" if len(got) < len(want) else
                  "over-split" if len(got) > len(want) else "wrong boundary"] += 1
            if len(misses) < 10:
                misses.append((surface, want, got))

    tot = len(cases)
    print(f"\nStage 2 (segmentation) vs DCS — {tot} scoreable fusions\n" + "─" * 62)
    print(f"  exact match                  {100*exact/tot:5.1f}%  ({exact}/{tot})")
    print(f"  not scoreable (compound reconstruction): {skipped}")
    print("\n  error shape:")
    for kind, n in shape.most_common():
        print(f"    {kind:16s} {n:4d}  {100*n/max(tot-exact,1):5.1f}% of errors")
    print("\n  by words per fusion:")
    for n in sorted(by_size):
        if by_size[n] >= 5:
            print(f"    {n}: {100*ok_by_size[n]/by_size[n]:5.1f}%  ({ok_by_size[n]:4d}/{by_size[n]:4d})")
    print("\n  sample misses:")
    for surface, want, got in misses[:6]:
        print(f"    {surface[:30]:30s} want={'+'.join(want)[:26]:26s} got={'+'.join(got)[:26]}")
    return exact / tot


if __name__ == "__main__":
    report()
