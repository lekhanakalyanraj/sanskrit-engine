# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Does the engine behave the same on the texts it exists to read? — Gītā vs DCS.

    python -m evals.corpora

Every other figure in this project is measured on Nyāya, Caraka and Sūryasiddhānta prose, because
that is what carries published morphological annotation. **The Gītā is not in DCS at all.** So the
open question has been whether any of those numbers describe the target material, and this answers
it by running the same measures over both.

What is comparable and what is not:

  * **Segmentation** is comparable — both corpora give a word split. Scored as token recall, not
    exact sequence match, because the two sources split compounds by different conventions and an
    exact-sequence score would mostly measure that disagreement rather than our accuracy.
  * **Coverage and confidence** need no ground truth at all, so they compare cleanly.
  * **Metre is not a corpus difference.** Three of the six DCS texts here (Nāṭyaśāstra,
    Sūryasiddhānta, Carakasaṃhitā) are themselves in verse, so a high anuṣṭubh rate is correct
    rather than a false positive — calling this set "prose" was an error in an earlier caption.
  * **Morphology** cannot be compared: the Gītā data has interpretive glosses ("in prescribed
    duties"), not case and number tags. Absence of a number here is honest, not an oversight.
"""
from __future__ import annotations

from agents.verifier import deterministic_signals
from core import analyze_sentence
from core.normalize import to_pausa, to_slp1
from core.recite import scan
from core.segment import segment
from knowledge.dictionary import attach_senses, build_db
from knowledge.ingest_dcs import DEFAULT_TEXTS, fetch
from knowledge.ingest_gita import load as load_gita


def _norm(words) -> set[str]:
    return {to_pausa(w) for w in words if w}


def _measure(name: str, samples: list[tuple[str, list[str]]]) -> dict:
    """samples = (devanagari sentence, reference word split)."""
    recalled = ref_total = 0
    tokens = with_lemma = with_gloss = 0
    conf = {"high": 0, "medium": 0, "low": 0}
    scanned = anustubh = 0

    for dev, reference in samples:
        if reference:
            got = _norm(segment(to_slp1(dev)))
            want = _norm(reference)
            recalled += len(got & want)
            ref_total += len(want)
        try:
            result = attach_senses(analyze_sentence(dev))
        except Exception:                                # noqa: BLE001 — a failure is a datum
            continue
        for t in result.tokens:
            tokens += 1
            with_lemma += bool(t.analysis and t.analysis.pos != "unknown")
            with_gloss += bool(t.senses)
        hard = deterministic_signals(result)
        conf["high" if not hard else "medium" if len(hard) == 1 else "low"] += 1
        s = scan(dev)
        if s.aksharas:
            scanned += 1
            anustubh += s.metre == "anuṣṭubh"

    n = max(len(samples), 1)
    return {
        "name": name, "sentences": len(samples), "tokens": tokens,
        "seg_recall": 100 * recalled / ref_total if ref_total else None,
        "lemma_cov": 100 * with_lemma / max(tokens, 1),
        "gloss_cov": 100 * with_gloss / max(tokens, 1),
        "high": 100 * conf["high"] / n,
        "anustubh": 100 * anustubh / max(scanned, 1),
    }


def main(limit: int = 300) -> None:
    build_db()

    gita = load_gita()[:limit]
    gita_samples = [(v.devanagari, v.words) for v in gita if v.devanagari and v.words]

    dcs_samples = []
    for s in fetch(DEFAULT_TEXTS):
        toks = [t for t in s.tokens if t.unsandhied and not t.in_compound]
        if s.text_iast and toks:
            dcs_samples.append((s.text_iast, [t.unsandhied for t in toks]))
        if len(dcs_samples) >= limit:
            break

    rows = [_measure("Bhagavadgītā", gita_samples), _measure("DCS (mixed verse+prose)", dcs_samples)]

    print(f"\n{'':22s} {'sents':>6s} {'tokens':>7s} {'seg recall':>11s} "
          f"{'lemma':>7s} {'gloss':>7s} {'high-conf':>10s} {'anuṣṭubh':>9s}")
    print("─" * 86)
    for r in rows:
        seg = f"{r['seg_recall']:.1f}%" if r["seg_recall"] is not None else "—"
        print(f"  {r['name']:20s} {r['sentences']:6d} {r['tokens']:7d} {seg:>11s} "
              f"{r['lemma_cov']:6.1f}% {r['gloss_cov']:6.1f}% {r['high']:9.1f}% {r['anustubh']:8.1f}%")
    print("\n  seg recall — reference words our segmentation also produced")
    print("  high-conf  — sentences with no hard parse signal")
    print("  anuṣṭubh   — of scanned lines identified as the śloka metre")


if __name__ == "__main__":
    main()
