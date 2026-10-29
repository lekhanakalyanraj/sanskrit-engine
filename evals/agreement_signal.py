# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Phase A — is adjacent-token agreement a usable signal? (STRUCTURAL-DISAMBIGUATION.md §6)

    python -m evals.agreement_signal

Builds no model. Answers whether Phase B is worth building:

  Q1  Does an adjective actually agree with a NEIGHBOUR in real Sanskrit, verse included — and how
      often would two unrelated words agree by chance? A signal is only a signal above its baseline.
  Q2  Ceiling: restricting each token to candidates agreeing with a neighbour's CORRECT reading,
      how much of the 22–26 pt gap is reachable at all?
  Q2b Realistic: the same idea with no oracle — a chain Viterbi over adjacent agreement. This is a
      minimal version of the actual proposal, so it estimates the real gain rather than a bound.
  Q4  Residual ambiguity: if agreement narrows 13 candidates to 4, the rest still needs a prior.
"""
from __future__ import annotations

import collections
import random

from core.morphology import analyze_candidates
from core.segment import _underlying
from knowledge.ingest_dcs import DEFAULT_TEXTS, fetch

CASE = {"Nom": "nominative", "Acc": "accusative", "Ins": "instrumental", "Dat": "dative",
        "Abl": "ablative", "Gen": "genitive", "Loc": "locative", "Voc": "vocative"}
GENDER = {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter"}
NUMBER = {"Sing": "singular", "Dual": "dual", "Plur": "plural"}


def gold_triple(tok):
    c, g, n = tok.feats.get("Case"), tok.feats.get("Gender"), tok.feats.get("Number")
    if c not in CASE or g not in GENDER or n not in NUMBER:
        return None
    return (CASE[c], GENDER[g], NUMBER[n])


def cand_triple(c):
    t = (c.features.get("case"), c.features.get("gender"), c.features.get("number"))
    return t if all(t) else None


def main() -> None:
    sents = fetch(DEFAULT_TEXTS)
    rows = []
    for s in sents:
        toks = [t for t in s.tokens if t.unsandhied and not t.in_compound]
        if len(toks) < 2:
            continue
        rows.append((toks, [gold_triple(t) for t in toks]))

    # ── Q1: adjacency signal vs chance ───────────────────────────────────────────────────────────
    adj_hit = adj_tot = 0
    adj_hit_ADJ = adj_tot_ADJ = 0
    rng = random.Random(0)
    chance_hit = chance_tot = 0
    for toks, golds in rows:
        for i, g in enumerate(golds):
            if g is None:
                continue
            nbrs = [golds[j] for j in (i - 1, i + 1) if 0 <= j < len(golds) and golds[j]]
            if not nbrs:
                continue
            hit = any(nb == g for nb in nbrs)
            adj_tot += 1; adj_hit += hit
            if toks[i].upos == "ADJ":
                adj_tot_ADJ += 1; adj_hit_ADJ += hit
        # baseline: same sentence, NON-adjacent pairs
        idx = [i for i, g in enumerate(golds) if g]
        for i in idx:
            far = [j for j in idx if abs(i - j) > 1]
            if far:
                chance_tot += 1
                chance_hit += golds[rng.choice(far)] == golds[i]

    print("\nQ1 — does a token agree with an ADJACENT token?\n" + "─" * 60)
    print(f"  any token, agrees with a neighbour   {100*adj_hit/adj_tot:5.1f}%  ({adj_hit}/{adj_tot})")
    print(f"  ADJECTIVES only                      {100*adj_hit_ADJ/max(adj_tot_ADJ,1):5.1f}%  "
          f"({adj_hit_ADJ}/{adj_tot_ADJ})")
    print(f"  chance baseline (non-adjacent pair)  {100*chance_hit/chance_tot:5.1f}%  "
          f"({chance_hit}/{chance_tot})")
    lift = 100*adj_hit_ADJ/max(adj_tot_ADJ,1) - 100*chance_hit/chance_tot
    print(f"  → adjectives exceed chance by {lift:+.1f} pt")

    # ── Q2 / Q4: does agreement narrow the candidate set, and is truth retained? ──────────────────
    before = after = kept = lost = 0
    n_tok = 0
    unique_after = unique_right = 0
    for toks, golds in rows:
        cls = [analyze_candidates(_underlying(t.unsandhied) or t.unsandhied) for t in toks]
        for i, (tok, g) in enumerate(zip(toks, golds)):
            if g is None:
                continue
            nbr = [golds[j] for j in (i - 1, i + 1) if 0 <= j < len(golds) and golds[j]]
            if not nbr:
                continue
            cands = cls[i]
            allowed = [c for c in cands if cand_triple(c) in nbr]
            n_tok += 1
            before += len(cands)
            if allowed:
                after += len(allowed)
                if any(cand_triple(c) == g for c in allowed): kept += 1
                else: lost += 1
                if len(allowed) == 1:
                    unique_after += 1
                    unique_right += cand_triple(allowed[0]) == g
            else:
                after += len(cands)

    print("\nQ2/Q4 — restricting candidates to agree with a neighbour's CORRECT reading\n" + "─" * 60)
    print(f"  mean candidates before   {before/n_tok:5.1f}")
    print(f"  mean candidates after    {after/n_tok:5.1f}")
    print(f"  truth retained           {100*kept/max(kept+lost,1):5.1f}%  ({kept}/{kept+lost})")
    print(f"  narrowed to exactly one  {unique_after}  of which correct {unique_right} "
          f"({100*unique_right/max(unique_after,1):.1f}%)")


if __name__ == "__main__":
    main()
