# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Faithfulness eval — score live LLM translations against the gold set.

The measurement harness for the LLM layer: run the real explainer over every gold sentence and
compare its translation to the hand-verified `gloss_en`, then report the verifier's verdict too.
This is what makes prompt/model changes *measurable* instead of vibes (PLAN.md test strategy).

Scoring is **semantic similarity** (cosine over BGE embeddings we already ship) rather than exact
match, because many translations are equally correct ("the boy eats fruit" / "a boy is eating
fruit"). It is a *relative regression signal*, not an absolute quality score — read the deltas
between runs, not the raw number.

    python -m evals.faithfulness              # all gold sentences
    python -m evals.faithfulness --limit 5    # quick pass
"""
from __future__ import annotations

import argparse
import statistics
from pathlib import Path

import yaml

from agents.explainer import build_grounding, explain
from agents.verifier import verify
from core import analyze_sentence
from knowledge.dictionary import attach_senses, build_db
from knowledge.vectorstore import _embed

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"


def load_gold() -> list[dict]:
    entries = []
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        for e in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if e.get("gloss_en"):
                entries.append(e)
    return entries


def similarity(a: str, b: str) -> float:
    """Cosine similarity between two texts (BGE embeddings are L2-normalised)."""
    va, vb = _embed([a, b])
    return sum(x * y for x, y in zip(va, vb))


def evaluate(limit: int | None = None) -> list[dict]:
    build_db()
    rows = []
    for entry in load_gold()[:limit]:
        sentence, reference = entry["sentence_dev"], entry["gloss_en"]
        try:
            result = attach_senses(analyze_sentence(sentence))
            expl = explain(result)
            verdict = verify(expl, build_grounding(result), result)
            rows.append({
                "id": entry["id"], "domain": entry.get("domain", "—"),
                "sentence": sentence, "reference": reference,
                "candidate": expl.translation,
                "similarity": round(similarity(expl.translation, reference), 3),
                "confidence": verdict.confidence, "grounded": verdict.grounded,
                "issues": verdict.issues,
            })
        except Exception as e:  # noqa: BLE001 — a failure is a result worth reporting
            rows.append({"id": entry["id"], "domain": entry.get("domain", "—"),
                         "sentence": sentence, "reference": reference,
                         "candidate": f"<ERROR: {e}>", "similarity": 0.0,
                         "confidence": "—", "grounded": False, "issues": [str(e)]})
    return rows


def report(rows: list[dict]) -> None:
    print(f"\n{'id':30s} {'sim':>5s}  {'conf':7s} {'gr':3s}  translation")
    print("-" * 100)
    for r in rows:
        gr = "✓" if r["grounded"] else "✗"
        print(f"{r['id'][:30]:30s} {r['similarity']:5.3f}  {r['confidence']:7s} {gr:3s}  {r['candidate'][:46]}")

    sims = [r["similarity"] for r in rows]
    grounded = sum(1 for r in rows if r["grounded"])
    print("-" * 100)
    print(f"n={len(rows)}  mean_similarity={statistics.mean(sims):.3f}  "
          f"median={statistics.median(sims):.3f}  min={min(sims):.3f}")
    print(f"grounded={grounded}/{len(rows)}  "
          f"confidence: " + ", ".join(
              f"{c}={sum(1 for r in rows if r['confidence'] == c)}" for c in ("high", "medium", "low")))

    weak = [r for r in rows if r["similarity"] < 0.75]
    if weak:
        print(f"\nweakest {len(weak)} (candidates for prompt tuning):")
        for r in weak:
            print(f"  [{r['similarity']:.3f}] {r['sentence']}")
            print(f"        ref : {r['reference']}")
            print(f"        got : {r['candidate']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    report(evaluate(ap.parse_args().limit))
