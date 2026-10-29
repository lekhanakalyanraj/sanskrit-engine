# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Faithfulness — translations scored against the VOICE policy, not against a reference gloss.

    python -m evals.faithfulness              # all gold sentences (needs a live LLM)
    python -m evals.faithfulness --limit 5

**What changed and why.** This eval used to score cosine similarity against the gold `gloss_en`.
That metric rated "The sage speaks the truth" at 1.000 and rated a layered, undomesticated reading
lower — it was optimising for the milked-out translation VOICE.md exists to prevent. Worse, the
premise was wrong: treating one terse English gloss as ground truth reinstates exactly the habit
that produced the history of confident Sanskrit mistranslation. There is no single correct English
for a Sanskrit line, so the reference had to go, not be improved.

What replaces it is a **constraint pass-rate**: VOICE.md's prohibitions, applied mechanically (see
`evals.policy`). A translation is not scored on how close it lands to one person's wording; it is
scored on whether it intervened — collapsed a technical term, resolved an open duality, padded,
imposed a devotional frame, dropped the question mark, asserted something no sense supports.

Two things this deliberately does NOT do:

  * It does not reward matching a reference. Two very different translations can both pass.
  * It does not claim to measure everything. "Does not shrink cosmic scale" and "does not simplify
    genuine difficulty" are real constraints that no regex should pretend to judge; they belong to
    the human review loop. A green run here means "no detectable intervention", never "good".

Confidence is reported alongside so that high-confidence violations stand out — a wrong answer
delivered confidently is the failure mode this project is built against.
"""
from __future__ import annotations

import argparse
import collections
from pathlib import Path

import yaml

from agents.explainer import build_grounding, explain
from agents.verifier import verify
from core import analyze_sentence
from evals.policy import RULES, check
from knowledge.dictionary import attach_senses, build_db

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"


def load_gold() -> list[dict]:
    entries = []
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        for e in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if e.get("sentence_dev"):
                entries.append(e)
    return entries


def evaluate(limit: int | None = None) -> list[dict]:
    build_db()
    rows = []
    for entry in load_gold()[:limit]:
        sentence = entry["sentence_dev"]
        try:
            result = attach_senses(analyze_sentence(sentence))
            expl = explain(result)
            verdict = verify(expl, build_grounding(result), result)
            rows.append({
                "id": entry["id"], "domain": entry.get("domain", "—"), "sentence": sentence,
                "translation": expl.translation,
                "violations": check(expl.translation, result),
                "confidence": verdict.confidence,
            })
        except Exception as exc:                          # noqa: BLE001 — a failure is a result
            rows.append({"id": entry["id"], "domain": entry.get("domain", "—"),
                         "sentence": sentence, "translation": f"<ERROR: {exc}>",
                         "violations": [], "confidence": "—", "error": str(exc)})
    return rows


def report(rows: list[dict]) -> int:
    errors = [r for r in rows if "error" in r]
    scored = [r for r in rows if "error" not in r]
    clean = [r for r in scored if not r["violations"]]

    print(f"\n{'id':28s} {'conf':7s} {'viol':>4s}  translation")
    print("─" * 96)
    for r in scored:
        n = len(r["violations"])
        print(f"{r['id'][:28]:28s} {r['confidence']:7s} {n:4d}  {r['translation'][:48]}")

    print("─" * 96)
    print(f"clean: {len(clean)}/{len(scored)}   ({100*len(clean)/max(len(scored),1):.0f}% with no "
          f"detectable intervention)")

    per_rule: collections.Counter = collections.Counter()
    for r in scored:
        for v in r["violations"]:
            per_rule[v.rule] += 1
    print("\nviolations by VOICE constraint:")
    for rule in RULES:
        mark = "·" if not per_rule[rule] else "✗"
        print(f"  {mark} {rule:34s} {per_rule[rule]}")

    # a violation delivered at high confidence is the worst case (EVAL-STRATEGY Layer 4)
    loud = [r for r in scored if r["violations"] and r["confidence"] == "high"]
    if loud:
        print(f"\n⚠ {len(loud)} HIGH-CONFIDENCE violations — confidently wrong is the failure mode:")
        for r in loud[:5]:
            print(f"    {r['id']}: {r['translation'][:60]}")
            for v in r["violations"][:3]:
                print(f"       [{v.rule}] {v.detail}")

    detail = [r for r in scored if r["violations"] and r["confidence"] != "high"]
    if detail:
        print(f"\nother violations ({len(detail)}):")
        for r in detail[:6]:
            print(f"  {r['id']}: {r['translation'][:58]}")
            for v in r["violations"][:3]:
                print(f"     [{v.rule}] {v.detail}")

    if errors:
        print(f"\n{len(errors)} sentences failed to run (is the LLM up?):")
        for r in errors[:3]:
            print(f"  {r['id']}: {r['error'][:70]}")
    return len(scored) - len(clean)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    raise SystemExit(0 if report(evaluate(ap.parse_args().limit)) == 0 else 1)
