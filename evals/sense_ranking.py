# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Does the sense we show FIRST actually say what the word means here?

Every other dictionary metric in this project measures *form* — is a gloss well-shaped, is it free
of apparatus. This one measures meaning, and it is the weakest number the engine has.

Ground truth is the Gītā's own `word_meanings` padapāṭha: a human editor's per-word gloss for 701
verses, independent of every dictionary we ingest.

This file scores THE SHIPPING PATH. It used to read raw rows out of the `sense` table, which skips
deduplication, the gaṇa preference and the curated particle glosses — and that made one comparison
come out exactly backwards: consensus ranking measured +1.2pt on raw rows and **-5.5pt** through
the engine, with 0 of 18 chapters improving, because the particles it destroys (39.0% -> 10.8%)
were invisible to a raw-row view. Everything here now goes through
`knowledge.dictionary.senses_for`, the same call the pipeline makes.

Two properties of the metric, stated rather than hidden:

  * It is LENIENT. An editor writes the contextual sense ("the land of dharma"), a dictionary the
    general one ("established order, usage, custom"). Demanding string equality would score every
    correct answer wrong, so a hit is content-word overlap — "did we surface the right region of
    meaning", not "did we phrase it identically". That is a weaker claim, and the honest one.
  * ENGLISH INFLECTION IS FOLDED. The editor glosses a finite Sanskrit verb with a finite English
    one ("spoke", "was", "blew") while dictionaries write the infinitive ("to speak", "to be",
    "to blow"). Left raw those never match, and verbs came out the worst word class in the corpus
    (19.6%) for a reason with nothing to do with Sanskrit. Folded, verbs sit level with nouns.

    python -m evals.sense_ranking
"""
from __future__ import annotations

import collections
import re
import statistics

from core.morphology import analyze_candidates
from core.normalize import to_slp1
from core.segment import _underlying
from knowledge.dictionary import senses_for
from knowledge.ingest_gita import load

_STOP = set("""a an the of to in and or with for by as is be its his her their that this from on at
which who whom one all not no any some such been being are was were do does did having have has""".split())

#: Irregular English verbs, folded so a finite gloss can meet an infinitive one.
_IRREGULAR = {
    "was": "be", "were": "be", "is": "be", "are": "be", "been": "be", "am": "be",
    "spoke": "speak", "spoken": "speak", "said": "say", "says": "say",
    "blew": "blow", "blown": "blow", "did": "do", "does": "do", "done": "do",
    "went": "go", "gone": "go", "goes": "go", "saw": "see", "seen": "see", "sees": "see",
    "took": "take", "taken": "take", "gave": "give", "given": "give",
    "knew": "know", "known": "know", "made": "make", "became": "become", "becomes": "become",
    "had": "have", "has": "have", "held": "hold", "stood": "stand", "struck": "strike",
    "slew": "slay", "slain": "slay", "fell": "fall", "felt": "feel", "found": "find",
    "got": "get", "kept": "keep", "left": "leave", "lost": "lose", "met": "meet",
    "ran": "run", "sang": "sing", "sat": "sit", "sent": "send", "shone": "shine",
    "shot": "shoot", "sprang": "spring", "thought": "think", "threw": "throw",
    "understood": "understand", "won": "win", "wrote": "write", "bore": "bear", "born": "bear",
    "drew": "draw", "drove": "drive", "ate": "eat", "eaten": "eat", "arose": "arise",
    "bound": "bind", "brought": "bring", "built": "build", "heard": "hear", "led": "lead",
}


def _toks(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zā-ž]+", text.lower()) if w not in _STOP and len(w) > 2}


def _raw_toks(text: str) -> set[str]:
    return set(re.findall(r"[a-zā-ž]+", text.lower()))


def _stem(word: str) -> str:
    """Crude English stem — it only has to make "spoke"/"speak" meet, not to be a lemmatiser."""
    w = _IRREGULAR.get(word, word)
    for suffix, keep in (("ing", 3), ("ed", 2), ("es", 2), ("s", 1)):
        if len(w) > 4 and w.endswith(suffix):
            base = w[:-keep]
            if base.endswith(("bb", "dd", "gg", "mm", "nn", "pp", "rr", "tt")):
                base = base[:-1]
            return base.rstrip("e") or w
    return w.rstrip("e") if len(w) > 4 else w


def _hit(ours: str, gold: str) -> bool:
    """Did we surface the right region of meaning?"""
    a, b = _toks(ours), _toks(gold)
    if not a or not b:                       # function words — compare without stopword removal
        a, b = _raw_toks(ours), _raw_toks(gold)
    if a & b:
        return True
    if {_stem(w) for w in a} & {_stem(w) for w in b}:
        return True
    # A proper noun is glossed by NAMING it: gold "Drupad" against ours "name of a king of the
    # Pāñcālas" is one claim seen from its two halves.
    return "name" in _raw_toks(ours) and gold.strip()[:1].isupper()


def covers(ours: str, gold: str, frac: float = 0.5) -> bool:
    """Did we cover the EDITOR's meaning? The primary metric.

    Scored over the GOLD's words, not ours, and that asymmetry is the whole point. The earlier
    metric asked only whether the two glosses shared *any* content word, which a longer gloss
    satisfies mechanically — and it was gameable to the point of absurdity: "pick the longest
    gloss", using no context and no grammar at all, scored 39.7% against the engine's 35.8% and
    beat every ranking strategy in this file. Anything tuned against that would be optimising
    verbosity.

    Requiring half the editor's own words to be covered removes the reward for padding: on this
    metric picking the longest gloss scores 27.5% against the engine's 29.2%, i.e. it now loses,
    which is the sanity check the old metric failed.
    """
    b = _toks(gold) or _raw_toks(gold)
    if not b:
        return False
    a = _toks(ours) or _raw_toks(ours)
    stem_a, stem_b = {_stem(w) for w in a}, {_stem(w) for w in b}
    if not stem_b:
        return False
    if len(stem_a & stem_b) / len(stem_b) >= frac:
        return True
    # A proper noun is glossed by NAMING it: gold "Drupad" against ours "name of a king of the
    # Pāñcālas" is one claim seen from its two halves.
    return "name" in _raw_toks(ours) and gold.strip()[:1].isupper()


def resolve(word: str):
    """word -> the analysis the engine would choose, or None.

    Looks up the LEMMA, not the surface form. Without that step the padapāṭha's inflected words
    (`jñānam`, `ucyate`, `mayi`, `karmāṇi`) count as missing vocabulary when we hold the stem
    perfectly well — it measured 44.7% "coverage" against a true 78%, and skewed the score onto
    the subset of words that happen already to be lemmas.
    """
    slp1 = to_slp1(word)
    for form in (slp1, _underlying(slp1), slp1.rstrip("H")):
        if not form:
            continue
        for cand in analyze_candidates(form)[:3]:
            if cand.pos != "unknown" and senses_for(cand):
                return cand
    return None


def report() -> None:
    verses = load()
    per_chapter: dict[object, list[int]] = collections.defaultdict(lambda: [0, 0])
    per_pos: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    n_words = covered = top1 = top3 = reachable = 0
    misses: list[tuple[str, str, str]] = []

    for verse in verses:
        chapter = getattr(verse, "chapter", None) or getattr(verse, "chapter_number", 0)
        for word, gold in zip(verse.words, verse.glosses):
            if not word or not gold.strip():
                continue
            n_words += 1
            analysis = resolve(word)
            if analysis is None:
                continue
            senses = senses_for(analysis)
            if not senses:
                continue
            covered += 1
            hit1 = covers(senses[0].gloss, gold)
            top1 += hit1
            top3 += any(covers(s.gloss, gold) for s in senses[:3])
            reachable += any(covers(s.gloss, gold) for s in senses)
            per_chapter[chapter][0] += hit1
            per_chapter[chapter][1] += 1
            per_pos[analysis.pos][0] += hit1
            per_pos[analysis.pos][1] += 1
            if not hit1 and len(misses) < 12:
                misses.append((word, gold[:30], senses[0].gloss[:38]))

    print(f"Sense accuracy vs the Gītā padapāṭha — {len(verses)} verses, via senses_for()")
    print("=" * 72)
    print(f"  words in ground truth   {n_words:,}")
    print(f"  resolved to a lemma     {covered:,}  ({covered / max(n_words, 1):.1%} coverage)")
    if not covered:
        print("\n  nothing resolved — cannot score")
        return
    print(f"\n  top-1  {top1 / covered:.1%}      top-3  {top3 / covered:.1%}"
          f"      reachable  {reachable / covered:.1%}")
    print(f"  ranking headroom: {(reachable - top1) / covered * 100:+.1f}pt "
          f"(the correct gloss is already in our data this often)")

    rates = [ok / n for ok, n in per_chapter.values() if n >= 30]
    if rates:
        print(f"\n  per-chapter top-1: mean {statistics.mean(rates):.1%}, "
              f"stdev {statistics.pstdev(rates):.1%}, "
              f"range {min(rates):.1%}–{max(rates):.1%}")
        print("  (a tight spread is what makes the headline trustworthy rather than a lucky slice)")

    print(f"\n  {'word type':12} {'top-1':>7} {'n':>8}")
    print("  " + "-" * 30)
    for pos, (ok, n) in sorted(per_pos.items(), key=lambda kv: -kv[1][1]):
        if n >= 30:
            print(f"  {pos:12} {ok / n:>6.1%} {n:>8,}")

    print("\n  misses (word | editor | ours):")
    for word, gold, ours in misses:
        print(f"    {word[:16]:17} {gold:31} {ours}")


if __name__ == "__main__":
    report()
