# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 4 at scale — kāraka roles against the Hyderabad gold corpus.

    python -m evals.uohyd_karaka

Until now the kāraka layer could only be checked against 71 DCS dependency tokens, because DCS
annotates morphology richly and syntax barely. This corpus annotates 26,295 tokens in the SAME
vocabulary the engine emits — kartā, karma, karaṇa, apādāna, adhikaraṇa, sambandha, viśeṣaṇa —
so for the first time the semantic layer can be measured rather than spot-checked.

Sentences arrive already split into words, so this isolates stage 4: segmentation errors cannot
leak in and inflate or deflate the number.
"""
from __future__ import annotations

import collections

from core.disambiguate import select
from core.karaka import build_karaka_edges
from core.models import Token as EngineToken
from core.morphology import analyze_candidates
from core.normalize import to_pausa
from core.segment import _underlying
from knowledge.ingest_uohyd import load


def report(limit: int | None = None) -> None:
    sents = load()[:limit]
    conf: collections.Counter = collections.Counter()
    scored = 0

    for sent in sents:
        words = [t.word for t in sent.tokens if t.word]
        if not (2 <= len(words) <= 25):
            continue
        forms = [_underlying(w) or w for w in words]
        analyses = select([analyze_candidates(f) for f in forms])
        tokens = [EngineToken(id=i, surface=to_pausa(f), surface_slp1=f, analysis=a)
                  for i, (f, a) in enumerate(zip(forms, analyses))]
        ours = {e.dependent: e.role for e in build_karaka_edges(tokens)}

        for i, gold in enumerate(t for t in sent.tokens if t.word):
            if gold.relation is None:
                continue                       # relation outside our vocabulary — not scored
            scored += 1
            conf[(gold.relation, ours.get(i))] += 1

    roles = ["kartā", "karma", "karaṇa", "sampradāna", "apādāna", "adhikaraṇa", "sambandha", "viśeṣaṇa"]
    correct = sum(conf[(r, r)] for r in roles)
    print(f"\nKāraka roles vs Hyderabad gold — {scored:,} annotated tokens\n" + "─" * 68)
    print(f"  exact role match   {100*correct/max(scored,1):5.1f}%  ({correct:,}/{scored:,})\n")
    print(f"  {'gold role':14s} {'n':>6s} {'we agree':>9s}   most common confusion")
    for r in roles:
        n = sum(v for (g, _), v in conf.items() if g == r)
        if not n:
            continue
        hit = conf[(r, r)]
        wrong = collections.Counter({o: v for (g, o), v in conf.items() if g == r and o != r})
        top = wrong.most_common(1)
        note = f"{top[0][0] or 'no edge'} ({top[0][1]})" if top else "—"
        print(f"  {r:14s} {n:6,} {100*hit/n:8.1f}%   {note}")


if __name__ == "__main__":
    report()
