# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""How much of the selection gap can Pāṇinian agreement constraints reach? (item 2)

    python -m evals.constraint_ceiling

Case sits at 74.0% against a 95.1% oracle and gender at 72.2% against 95.7%. The open question is
whether that 21–24 points is reachable by CONSTRAINTS — agreement, government, one-karma — or
whether it needs something else. Answering it decides whether a constraint parser is worth weeks.

**What this can and cannot measure.** The clean experiment takes DCS's dependency annotations as an
oracle for structure and asks what the constraints then recover. Our slice carries only 449
annotated tokens and **8 `amod` links**, so adjective agreement — the constraint most likely to
matter — cannot be tested that way at all.

What is measurable is a bound from the other side. Rather than "agrees with THIS word", ask
"agrees with SOME correctly-read word in the same sentence". That is:

  * **weaker** than a parser, which knows which pair is linked;
  * **stronger** than Phase A, which assumed adjacency and converted to +0.4;

so it brackets the answer. If even this upper bound is small, a parser cannot rescue it and the
constraints are not the bottleneck. If it is large, the gap really is structural and the parser is
the way to reach it.
"""
from __future__ import annotations

import collections

from core.morphology import analyze_candidates
from core.disambiguate import select
from core.segment import _underlying
from evals.dcs_morphology import CASE, GENDER, NUMBER
from knowledge.ingest_dcs import DEFAULT_TEXTS, fetch

FIELDS = (("case", CASE, "Case"), ("gender", GENDER, "Gender"), ("number", NUMBER, "Number"))


def _gold(tok) -> tuple | None:
    """A token's correct (case, gender, number), or None when DCS does not annotate all three."""
    out = []
    for field, mapping, key in FIELDS:
        raw = tok.feats.get(key)
        if raw not in mapping:
            return None
        out.append(mapping[raw])
    return tuple(out)


def _triple(cand) -> tuple | None:
    t = (cand.features.get("case"), cand.features.get("gender"), cand.features.get("number"))
    return t if all(t) else None


def report(texts: list[str] | None = None) -> None:
    sents = fetch(texts or DEFAULT_TEXTS)

    stats = collections.Counter()
    before_n = after_n = tokens = 0

    for sent in sents:
        toks = [t for t in sent.tokens if t.unsandhied and not t.in_compound]
        golds = [_gold(t) for t in toks]
        if sum(g is not None for g in golds) < 2:
            continue
        forms = [_underlying(t.unsandhied) or t.unsandhied for t in toks]
        cls = [analyze_candidates(f) for f in forms]
        chosen = select(cls)

        # every correct reading in the sentence, as licensing partners
        partners = {g for g in golds if g}

        for i, (tok, gold, cands, pick) in enumerate(zip(toks, golds, cls, chosen)):
            if gold is None:
                continue
            tokens += 1
            stats["baseline"] += _triple(pick) == gold

            # CONSTRAINT: keep only readings that agree fully with some other correct reading
            others = partners - {gold} if len(partners) > 1 else partners
            allowed = [c for c in cands if _triple(c) in others]
            before_n += len(cands)
            after_n += len(allowed) if allowed else len(cands)

            if not allowed:
                stats["no_partner"] += 1
                stats["ceiling"] += _triple(pick) == gold      # constraint silent, keep baseline
                continue
            stats["constrained"] += 1
            stats["survives"] += any(_triple(c) == gold for c in allowed)
            # best case for the constraint: it picks correctly whenever the truth survives
            stats["ceiling"] += any(_triple(c) == gold for c in allowed)

    n = max(tokens, 1)
    print(f"\nConstraint ceiling — full case+gender+number agreement, {tokens} annotated tokens")
    print("─" * 74)
    print(f"  today, all three correct at once      {100*stats['baseline']/n:5.1f}%")
    print(f"  CEILING if the constraint always won  {100*stats['ceiling']/n:5.1f}%")
    print(f"    → headroom the constraint can reach  {100*(stats['ceiling']-stats['baseline'])/n:+5.1f} pt")
    print()
    print(f"  tokens the constraint speaks to       {stats['constrained']} ({100*stats['constrained']/n:.0f}%)")
    print(f"  tokens with no agreeing partner       {stats['no_partner']} ({100*stats['no_partner']/n:.0f}%)")
    print(f"  truth survives the filter             {100*stats['survives']/max(stats['constrained'],1):5.1f}%")
    print(f"  candidates per token   {before_n/n:4.1f} → {after_n/n:4.1f}")
    print("\n  This is an UPPER bound: it assumes the constraint always picks correctly among the")
    print("  readings it allows, and that a partner anywhere in the sentence licenses agreement.")
    print("  A real parser knows WHICH word agrees, so it scores lower, never higher.")


if __name__ == "__main__":
    report()
