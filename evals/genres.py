# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Per-GENRE and per-ERA accuracy, because one aggregate number hides where the engine breaks.

Everything here was tuned against DCS śāstra prose — logic, medicine, astronomy, drama — and the
aggregate said case was 73.9%. Running the Kena Upaniṣad put it at 58.7%. Nothing regressed; we
had simply never measured a second register, and a heuristic fitted to one corpus was being
reported as if it were a property of Sanskrit.

That is the failure mode this file exists to prevent. A rule that helps śāstra prose and hurts
Upaniṣadic verse is not wrong, but it must be *known* to be genre-dependent rather than discovered
later. Add a text here and its genre is measured separately from then on.

    python -m evals.genres              # every registered corpus
    python -m evals.genres upanisad     # one band
"""
from __future__ import annotations

import collections
import sys
from dataclasses import dataclass

from core.disambiguate import select
from core.morphology import analyze_candidates
from core.segment import _underlying
from knowledge.ingest_dcs import fetch

_CASE = {"Nom": "nominative", "Acc": "accusative", "Ins": "instrumental", "Dat": "dative",
         "Abl": "ablative", "Gen": "genitive", "Loc": "locative", "Voc": "vocative"}


@dataclass(frozen=True)
class Corpus:
    name: str          # the DCS directory / local cache name
    band: str          # the register we group by
    era: str           # roughly when the language is from
    note: str


#: Registered corpora. `band` is what gets averaged; keep bands small and homogeneous, because the
#: whole point is that mixing registers hides the variance rather than reporting it.
CORPORA: list[Corpus] = [
    Corpus("Kenopanisad",        "upanisad", "early Vedic prose+verse", "Talavakāra; JUB 4.18-21"),
    Corpus("Kauṣītakyupaniṣad",  "upanisad", "early Vedic prose",       "philosophy"),
    Corpus("Nyāyasūtra",         "sutra",    "classical",               "logic; terse sūtra style"),
    Corpus("Arthaśāstra",        "sutra",    "classical",               "statecraft"),
    Corpus("Carakasaṃhitā",      "sastra",   "classical",               "medicine"),
    Corpus("Sūryasiddhānta",     "sastra",   "classical",               "astronomy; verse"),
    Corpus("Nāṭyaśāstra",        "sastra",   "classical",               "drama, aesthetics"),
    # ── Vedic: the oldest layer. Different accent, archaic morphology, injunctives and
    #    subjunctives the classical language dropped, and word order far freer than prose.
    Corpus("Ṛgveda",             "vedic",    "Vedic (oldest)",          "hymn; archaic morphology"),
    Corpus("Atharvaveda (Śaunaka)", "vedic", "Vedic",                   "hymn; charms"),
    # ── Kāvya: classical poetry. Long compounds, deliberately marked word order, and a
    #    vocabulary chosen for sound as much as sense. Kirātārjunīya is the hard end on purpose.
    Corpus("Meghadūta",          "kavya",    "classical",               "Kālidāsa; lyric"),
    Corpus("Kumārasaṃbhava",     "kavya",    "classical",               "Kālidāsa; epic poem"),
    Corpus("Kirātārjunīya",      "kavya",    "classical",               "Bhāravi; dense compounds"),
]


def _score(name: str) -> dict | None:
    """Per-field accuracy for one corpus, plus its dominant case confusion."""
    try:
        sents = fetch([name])
    except Exception:                                  # noqa: BLE001 — a missing corpus is not fatal
        return None
    if not sents:
        return None

    ok = collections.Counter()
    tot = collections.Counter()
    conf = collections.Counter()
    for s in sents:
        toks = [t for t in s.tokens if t.unsandhied and not t.in_compound]
        if not toks:
            continue
        forms = [_underlying(t.unsandhied) or t.unsandhied for t in toks]
        chosen = select([analyze_candidates(f) for f in forms])
        for t, a in zip(toks, chosen):
            feats = t.feats or {}
            if t.lemma:
                tot["lemma"] += 1
                ok["lemma"] += (a.lemma.split("#")[0] == t.lemma)
            gold_case = _CASE.get(feats.get("Case", ""))
            if gold_case:
                tot["case"] += 1
                ours = a.features.get("case")
                if ours == gold_case:
                    ok["case"] += 1
                else:
                    conf[(gold_case, ours or "none")] += 1
            if feats.get("Number"):
                tot["number"] += 1
                ok["number"] += (a.features.get("number", "")[:3].lower()
                                 == feats["Number"][:3].lower())
    if not tot["case"]:
        return None
    worst, worst_n = (conf.most_common(1) or [(("", ""), 0)])[0]
    return {"n": sum(len(s.tokens) for s in sents),
            "lemma": ok["lemma"] / max(tot["lemma"], 1),
            "case": ok["case"] / tot["case"],
            "number": ok["number"] / max(tot["number"], 1),
            "worst": f"{worst[0][:3]}->{worst[1][:3]}",
            "worst_share": worst_n / tot["case"]}


def report(band: str | None = None) -> None:
    rows = []
    for c in CORPORA:
        if band and c.band != band:
            continue
        s = _score(c.name)
        if s:
            rows.append((c, s))

    print(f"\n{'corpus':22} {'band':9} {'tokens':>7} {'lemma':>7} {'case':>7} {'number':>7}   worst confusion")
    print("=" * 96)
    by_band: dict[str, list] = collections.defaultdict(list)
    for c, s in rows:
        by_band[c.band].append(s)
        print(f"{c.name[:21]:22} {c.band:9} {s['n']:>7,} {s['lemma']:>7.1%} {s['case']:>7.1%} "
              f"{s['number']:>7.1%}   {s['worst']} {s['worst_share']:.1%}")

    print("-" * 96)
    for b, ss in sorted(by_band.items()):
        print(f"{'  BAND ' + b:22} {'':9} {sum(x['n'] for x in ss):>7,} "
              f"{sum(x['lemma'] for x in ss)/len(ss):>7.1%} "
              f"{sum(x['case'] for x in ss)/len(ss):>7.1%} "
              f"{sum(x['number'] for x in ss)/len(ss):>7.1%}")

    if len(by_band) > 1:
        cases = {b: sum(x["case"] for x in ss) / len(ss) for b, ss in by_band.items()}
        hi, lo = max(cases, key=cases.get), min(cases, key=cases.get)
        print(f"\n  spread across bands: {cases[hi]:.1%} ({hi}) vs {cases[lo]:.1%} ({lo}) "
              f"= {(cases[hi]-cases[lo])*100:.1f}pt")
        print("  A single aggregate number would report the average and hide this.")


if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else None)
