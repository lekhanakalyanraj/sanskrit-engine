# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage-attribution report — per-stage accuracy, and *where* each failure begins.

The problem this solves: when a translation came out wrong, nothing told us which stage lost it.
`bhāva` rendered as "light" was a **morphology** failure, but it only surfaced as a bad English
sentence, found by hand. Errors compound through the pipeline; this measures each link separately
and, for every failing sentence, names the EARLIEST stage that broke.

    python -m evals.stages            # all gold entries
    python -m evals.stages --verbose  # also print each failure's detail
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from core import analyze_sentence
from core.normalize import to_devanagari, to_slp1
from knowledge.dictionary import attach_senses, build_db

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"
STAGES = ["normalize", "segment", "lemma", "pos", "case", "karaka", "senses"]


def load_gold() -> list[dict]:
    out = []
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        for entry in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if entry.get("tokens"):
                out.append(entry)
    return out


def check(entry: dict) -> dict:
    """Compare one gold entry against the engine, stage by stage.

    Each stage records (correct, total) so accuracy is measured per link, plus the failures
    themselves so a human can see what actually differed.
    """
    res: dict = {"id": entry["id"], "stages": {s: [0, 0] for s in STAGES}, "detail": {}}
    dev = entry["sentence_dev"]

    def score(stage: str, ok: bool, note: str = "") -> None:
        res["stages"][stage][0] += int(ok)
        res["stages"][stage][1] += 1
        if not ok and note:
            res["detail"].setdefault(stage, []).append(note)

    slp1 = to_slp1(dev)
    score("normalize", to_devanagari(slp1) == dev, f"round-trip: {dev!r}")

    try:
        parsed = attach_senses(analyze_sentence(dev))
    except Exception as exc:                                     # noqa: BLE001
        score("segment", False, f"crashed: {exc}")
        return res

    got = [t.surface_slp1 for t in parsed.tokens]
    want = [t["slp1"] for t in entry["tokens"]]
    score("segment", got == want, f"got {got} want {want}")
    if got != want:
        return res                                               # later stages are unmeasurable

    for token, gold_tok in zip(parsed.tokens, entry["tokens"]):
        a = token.analysis
        lemma = (a.lemma if a else "").split("#")[0]
        score("lemma", lemma == gold_tok["lemma"], f"{gold_tok['slp1']}: {lemma} ≠ {gold_tok['lemma']}")
        score("pos", bool(a) and a.pos == gold_tok["pos"], f"{gold_tok['slp1']}: {a.pos if a else '—'} ≠ {gold_tok['pos']}")
        if "case" in gold_tok:
            got_case = a.features.get("case") if a else None
            score("case", got_case == gold_tok["case"], f"{gold_tok['slp1']}: {got_case} ≠ {gold_tok['case']}")
        score("senses", bool(token.senses), f"{gold_tok['slp1']}: no dictionary sense")

    got_edges = {(parsed.tokens[e.dependent].surface_slp1, e.role) for e in parsed.edges}
    want_edges = {(t["slp1"], t["karaka"]) for t in entry["tokens"] if "karaka" in t}
    score("karaka", got_edges == want_edges, f"got {sorted(got_edges)} want {sorted(want_edges)}")
    return res


def report(verbose: bool = False) -> int:
    build_db()
    gold = load_gold()
    results = [check(e) for e in gold]

    totals = {s: [0, 0] for s in STAGES}
    for r in results:
        for stage, (ok, n) in r["stages"].items():
            totals[stage][0] += ok
            totals[stage][1] += n

    print(f"\nStage accuracy over {len(gold)} gold sentences\n" + "─" * 58)
    for stage in STAGES:
        ok, n = totals[stage]
        if not n:
            continue
        pct = 100 * ok / n
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {stage:10s} {bar} {pct:5.1f}%   ({ok}/{n})")

    # earliest failing stage per sentence — this is the attribution
    broken: dict[str, list[str]] = {}
    for r in results:
        for stage in STAGES:
            ok, n = r["stages"][stage]
            if n and ok < n:
                broken.setdefault(stage, []).append(r["id"])
                break
    print("─" * 58)
    if broken:
        print("Earliest failing stage:")
        for stage in STAGES:
            if stage in broken:
                ids = broken[stage]
                print(f"  {stage:10s} {len(ids):2d}  {', '.join(ids[:4])}{' …' if len(ids) > 4 else ''}")
    else:
        print("All gold sentences pass every stage.")

    if verbose:
        for r in results:
            if r["detail"]:
                print(f"\n{r['id']}")
                for stage, notes in r["detail"].items():
                    for note in notes[:4]:
                        print(f"   [{stage}] {note}")
    return sum(len(v) for v in broken.values())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    raise SystemExit(0 if report(ap.parse_args().verbose) == 0 else 1)
