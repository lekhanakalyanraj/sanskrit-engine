# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Layer 4 — is the engine's confidence honest?

    python -m evals.calibration

The contract, and the whole reason this project exists:

    When the engine says HIGH confidence, it must be right.
    When it is unsure, it must say so.

Sanskrit's history is not one of tools that were sometimes wrong — every tool is sometimes wrong.
It is a history of translations that were **confidently** wrong, and were trusted because nothing
distinguished a solid reading from a guess. An error at low confidence is a limitation, honestly
declared. An error at high confidence is a lie the engine told, and those are release blockers.

This measures `P(correct | confidence)` on ground truth we did not author. Confidence comes from
`verifier.deterministic_signals`, which is pure — no model, no network — so calibration runs over
every DCS sentence rather than a handful the LLM had time for.

**No Expected Calibration Error is reported.** ECE needs numeric probabilities, and we have three
ordinal labels; inventing high=0.9 / medium=0.6 would manufacture precision the signal does not
have — pseudo-precision being the exact vice this document keeps catching. What is reported is what
the contract actually asserts: accuracy per bucket, whether it *decreases* monotonically, the
separation between high and low, and every high-confidence error by name.
"""
from __future__ import annotations

import collections

from agents.verifier import deterministic_signals
from core import analyze_sentence
from core.models import ParseResult, Token
from core.morphology import analyze_candidates
from core.normalize import to_pausa
from core.disambiguate import select
from core.segment import _underlying, segment
from evals.dcs_morphology import CASE
from knowledge.dictionary import attach_senses, build_db
from knowledge.ingest_dcs import DEFAULT_TEXTS, Sentence, fetch

LEVELS = ["high", "medium", "low"]


def confidence_of(result: ParseResult) -> str:
    """The same ladder `verify()` applies: hard parse signals can only lower confidence."""
    hard = deterministic_signals(result)
    return "high" if not hard else ("medium" if len(hard) == 1 else "low")


def _parse(sent: Sentence) -> ParseResult:
    """Build a ParseResult from DCS's own padapatha, so this measures the reading, not the split."""
    forms = [_underlying(t.unsandhied) or t.unsandhied
             for t in sent.tokens if t.unsandhied and not t.in_compound]
    analyses = select([analyze_candidates(f) for f in forms])
    tokens = [Token(id=i, surface=to_pausa(f), surface_slp1=f, analysis=a)
              for i, (f, a) in enumerate(zip(forms, analyses))]
    return attach_senses(ParseResult(sentence_devanagari="", sentence_slp1=" ".join(forms),
                                     tokens=tokens, edges=[]))


def report(texts: list[str] | None = None) -> int:
    build_db()
    sents = fetch(texts or DEFAULT_TEXTS)

    hits: collections.Counter = collections.Counter()
    totals: collections.Counter = collections.Counter()
    lemma_hits: collections.Counter = collections.Counter()
    lemma_totals: collections.Counter = collections.Counter()
    case_hits: collections.Counter = collections.Counter()
    case_totals: collections.Counter = collections.Counter()
    seg_hits: collections.Counter = collections.Counter()
    seg_totals: collections.Counter = collections.Counter()
    loud: list[tuple[str, str, str]] = []

    for sent in sents:
        scored = [t for t in sent.tokens if t.unsandhied and not t.in_compound]
        if not scored:
            continue
        result = _parse(sent)
        level = confidence_of(result)

        # morphology correctness, per token — lemma and case tracked SEPARATELY. Requiring both and
        # then printing only the lemma made case failures read as lemma mismatches
        # (`arTam want arTa got arTa`), which is a reporting lie about our own errors.
        for tok, parsed in zip(scored, result.tokens):
            a = parsed.analysis
            got_lemma = a.lemma.split("#")[0] if a else None
            want_case = CASE.get(tok.feats.get("Case", ""))
            got_case = a.features.get("case") if a else None
            lemma_ok = got_lemma == tok.lemma
            case_ok = want_case is None or got_case == want_case

            lemma_totals[level] += 1
            lemma_hits[level] += lemma_ok
            if want_case:
                case_totals[level] += 1
                case_hits[level] += case_ok

            totals[level] += 1
            hits[level] += lemma_ok and case_ok
            if level == "high" and not (lemma_ok and case_ok) and len(loud) < 40:
                field = "lemma" if not lemma_ok else "case"
                want = tok.lemma if not lemma_ok else want_case
                got = got_lemma if not lemma_ok else got_case
                loud.append((tok.unsandhied, field, str(want), str(got)))

        # segmentation correctness, on the fusions with trustworthy targets
        real = {t.unsandhied for t in sent.tokens if t.unsandhied}
        for surface, parts in sent.fusions:
            if not all(p in real for p in parts):
                continue
            seg_totals[level] += 1
            seg_hits[level] += [to_pausa(w) for w in segment(surface)] == [to_pausa(p) for p in parts]

    print("\nCalibration — P(correct | confidence), on DCS ground truth")
    print("=" * 66)
    for name, h, t in (("lemma", lemma_hits, lemma_totals),
                       ("case", case_hits, case_totals),
                       ("segmentation", seg_hits, seg_totals)):
        print(f"\n  {name}")
        print(f"    {'confidence':12s} {'accuracy':>10s} {'n':>8s}")
        accs = []
        for level in LEVELS:
            if not t[level]:
                continue
            acc = h[level] / t[level]
            accs.append(acc)
            bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
            print(f"    {level:12s} {100*acc:9.1f}% {t[level]:8d}  {bar}")
        if len(accs) >= 2:
            monotone = all(a >= b - 1e-9 for a, b in zip(accs, accs[1:]))
            print(f"    {'monotone (high ≥ medium ≥ low)':38s} {'✓ yes' if monotone else '✗ NO'}")
            print(f"    {'separation (high − low)':38s} {100*(accs[0]-accs[-1]):+.1f} pt")

    n_loud = totals["high"] - hits["high"]
    print("\n" + "=" * 66)
    if n_loud:
        print(f"⚠ {n_loud} HIGH-CONFIDENCE errors ({100*n_loud/max(totals['high'],1):.1f}% of high-confidence "
              f"tokens). These are the release blockers — a wrong answer delivered\n"
              f"  confidently is the failure mode this engine exists to avoid.")
        by_field = collections.Counter(f for _, f, _, _ in loud)
        print(f"  failing field among the sample: "
              + ", ".join(f"{k}={v}" for k, v in by_field.most_common()))
        for form, field, want, got in loud[:8]:
            print(f"    {form:18s} {field:6s} want {want:16s} got {got}")
    else:
        print("No high-confidence errors.")
    return n_loud


if __name__ == "__main__":
    report()
