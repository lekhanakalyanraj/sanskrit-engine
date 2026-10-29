# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 3 (symbolic) — dictionary lookup: lemma → English sense(s).

The deterministic *symbolic* half of retrieval: exact lookup by lemma, no ML. Backed by SQLite
(the architecture's symbolic store; Postgres later at scale). Seeded from dictionary.yaml now;
bulk Monier-Williams loads into the same `sense` table (see README) with source="MW".

    from knowledge.dictionary import lookup, attach_senses
    lookup("jala")            # [Sense(source="seed", gloss="water")]
    attach_senses(parse)      # fills each token.senses in a ParseResult
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml

from core.models import ParseResult, Sense

_HERE = Path(__file__).resolve().parent
_SEED = _HERE / "dictionary.yaml"
_DB = _HERE / "sanskrit.db"

_HOMONYM = re.compile(r"#\d+$")  # lexicon marks homonyms as e.g. 'pA#1'


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS sense (lemma TEXT NOT NULL, source TEXT NOT NULL, gloss TEXT NOT NULL)")
    # `gender` is the dictionary's own marker for THIS sense (m./f./n./mfn.), kept as a column
    # rather than left in the gloss text. It is the nominal counterpart of the verb's gaṇa: the
    # morphology knows what gender the FORM is, the dictionary knows what gender each SENSE is,
    # and homonymous stems differ in exactly that. Added late, so the column is nullable and
    # every reader must tolerate NULL.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sense)")}
    if "gender" not in cols:
        conn.execute("ALTER TABLE sense ADD COLUMN gender TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sense_lemma ON sense (lemma)")


def build_db() -> None:
    """(Re)load the seed lexicon (source='seed'). Leaves other sources (e.g. 'MW') intact."""
    entries = yaml.safe_load(_SEED.read_text(encoding="utf-8")) or {}
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source = 'seed'")
        conn.executemany(
            "INSERT INTO sense (lemma, source, gloss) VALUES (?, 'seed', ?)",
            list(entries.items()),
        )
        conn.commit()
    finally:
        conn.close()


def _conn() -> sqlite3.Connection:
    if not _DB.exists():
        build_db()
    return sqlite3.connect(_DB)


#: Vowel junctions Sanskrit resolves inside a word. The kosha hands us prefixed roots with the
#: junction UNAPPLIED — `ava`+`āp` arrives as `avaAp` where the word is `avāp` — so the dictionary
#: is searched for a form that does not exist. `prāp` ("obtain") has 15 senses and was invisible.
_INTERNAL_SANDHI = (
    ("aA", "A"), ("aa", "A"), ("AA", "A"), ("Aa", "A"),   # savarṇa-dīrgha
    ("ii", "I"), ("iI", "I"), ("Ii", "I"),
    ("uu", "U"), ("uU", "U"), ("Uu", "U"),
    ("ai", "e"), ("aI", "E"), ("au", "o"), ("aU", "O"),   # guṇa
    ("af", "ar"), ("af", "ar"),
)


def _resolve_sandhi(lemma: str) -> str | None:
    """The lemma with its internal vowel junction applied, or None if there is nothing to apply."""
    for junction, resolved in _INTERNAL_SANDHI:
        if junction in lemma:
            return lemma.replace(junction, resolved, 1)
    return None


def lookup(lemma: str) -> list[Sense]:
    """Senses for a lemma (SLP1). Homonym markers are stripped before lookup."""
    lemma = _HOMONYM.sub("", lemma)
    conn = _conn()
    try:
        rows = conn.execute(
            # Order is deliberate: curated seed first, then APTE, then Monier-Williams. Apte is a
            # reader's dictionary — short glosses written for construing a line — while MW is an
            # encyclopaedic reference. For someone reading a text, Apte answers the question they
            # actually asked, so it should be what they see first.
            "SELECT source, gloss, gender FROM sense WHERE lemma = ? "
            # Order of authority. The Dhātupāṭha is Pāṇini's own statement of what a root means, and the
            # 19th-century lexicographers are downstream of it — so for a BASE root it outranks them.
            # A PREFIXED form is different: Vidyut inherits the base artha across prefixes, so
            # `parābhū` would read "to exist" when it means "to perish", and there a dictionary that
            # recorded the prefixed sense must win. Our own curated seed stays first as deliberate
            # human work.
            # `llm` sits directly below the curated seed and above every 19th-century lexicon.
            # It is a short plain gloss written from a model's own knowledge of the stem, with no
            # Monier-Williams text and no verse shown to it — see knowledge/ingest_llm_sense.py.
            # Measured on the Gītā padapāṭha it takes top-1 from 29.4% to 38.6%, and nouns (the
            # bulk, 5,678 of 7,474 tokens) from 21.9% to 33.7%. It is placed BELOW the hand-curated
            # particle glosses deliberately: the model gave `ca`, the commonest word in the
            # language, as "to give, to grant", and letting it override curation costs 5 points.
            # The Dhātupāṭha stays ABOVE `llm`. Placing the model above it scores 38.8% against
            # 38.5% and leaves verbs identical at 26.6% — 0.3pt, which is not a reason to put a
            # 7B model's guess ahead of Pāṇini's own statement of what a root means.
            "ORDER BY CASE source WHEN 'seed' THEN 0 WHEN 'dhatupatha' THEN 1 "
            "WHEN 'llm' THEN 2 "
            "WHEN 'macdonell' THEN 3 WHEN 'apte' THEN 4 "
            "WHEN 'dhatupatha-upasarga' THEN 5 ELSE 6 END, source",
            (lemma,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        resolved = _resolve_sandhi(lemma)
        if resolved and resolved != lemma:
            return lookup(resolved)
    senses = _demote_llm_for_roots(
        dedupe_senses([Sense(source=s, gloss=g, gender=gd) for s, g, gd in rows]))
    from .curation import apply_rules            # human corrections layered on generated data
    return apply_rules(lemma, senses)



#: Three dictionaries independently describing one word restate the same meaning repeatedly: a
#: Gītā word carries 20.4 senses on average. Showing "guarding, protecting" and "guarding,
#: protecting." as two entries is noise.
#:
#: This removes RESTATEMENTS only; it never reorders. The first statement of a meaning is kept and
#: later ones dropped, so the authority ordering above is untouched and the sense shown first
#: cannot change. Ranking senses by cross-dictionary consensus WAS tried and measured 3.7pt worse
#: than authority order (`evals/sense_ranking.py`), so nothing here claims one sense beats another
#: — only that two are the same.
#:
#: The rule is deliberately conservative, and the reason is a bug this file already had. A single
#: shared word is NOT sameness. The seed gloss for `pā` is "to drink" — one content word — so a
#: containment score subsumed every gloss mentioning drinking, and silently deleted:
#:
#:     'to drink (√pA, pAne, BvAdi)'        the Dhātupāṭha root citation
#:     'cause to drink'                     the CAUSATIVE — a different meaning
#:     'des. wish to drink, be thirsty'     the DESIDERATIVE — also different
#:
#: leaving `pā` looking like a single root meaning "protect". So: at least TWO shared content
#: words, and containment only counts when the smaller gloss has three or more — a short gloss must
#: never swallow a longer one.
#:
#: Measured on the 4,248 Gītā words with a known lemma:
#:
#:     rule                          top-1   top-3   senses/word   removed   pā roots
#:     none                          29.1%   42.5%          20.4      0.0%   both
#:     1 shared word (the bug)       29.1%   42.9%          12.9     36.9%   drink LOST
#:     2 shared, containment>=3      29.1%   42.5%          17.7     13.4%   both OK
#:
#: The aggressive setting looks better on every number the benchmark reports and is wrong: top-1
#: and top-3 cannot see a fifth sense being deleted. 13.4% of genuine restatement is the real
#: figure; the other 23 points were meaning.
_DEDUP_THRESHOLD = 0.50
_DEDUP_MIN_SHARED = 2
_DEDUP_MIN_CONTAINMENT_SIZE = 3

_DEDUP_STOP = frozenset("""a an the of to in and or with for by as is be its his her their that
this from on at which who whom one all not no any some such been being are was were do does did""".split())


def _content_words(gloss: str) -> set[str]:
    import re
    return {w for w in re.findall(r"[a-zā-ž]+", gloss.lower())
            if w not in _DEDUP_STOP and len(w) > 2}


def dedupe_senses(senses: list[Sense], threshold: float = _DEDUP_THRESHOLD) -> list[Sense]:
    """Drop senses that restate one already listed. Order is preserved exactly."""
    kept: list[Sense] = []
    kept_tokens: list[set[str]] = []
    for sense in senses:
        tokens = _content_words(sense.gloss)
        if not tokens:                      # nothing to compare on — keep it rather than guess
            kept.append(sense)
            kept_tokens.append(set())
            continue
        duplicate = False
        for seen in kept_tokens:
            shared = len(tokens & seen)
            if shared < _DEDUP_MIN_SHARED:
                continue
            jaccard = shared / len(tokens | seen)
            smaller = min(len(tokens), len(seen))
            containment = shared / smaller if smaller >= _DEDUP_MIN_CONTAINMENT_SIZE else 0.0
            if max(jaccard, containment) >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(sense)
            kept_tokens.append(tokens)
    return kept


def _demote_llm_for_roots(senses: list[Sense]) -> list[Sense]:
    """A reader's dictionary outranks the model for VERBAL ROOTS. Order is otherwise untouched.

    Prefixed verbs are idiomatic and the model glosses them COMPOSITIONALLY. `parābhū` is parā +
    bhū, so it answered "beyond, arise" — but the verb means "to perish, to be defeated", which no
    amount of adding the parts together reaches. Apte records the prefixed sense; the model
    reconstructs it and gets it wrong. That is precisely what
    `test_a_readers_dictionary_outranks_the_inherited_artha` exists to catch, and it caught it.

    The condition is "this lemma is a root" — it carries a Dhātupāṭha sense — rather than "this
    token is a verb", because the rule is about the LEMMA and `lookup()` has no analysis to
    consult. It therefore holds on both paths, the pipeline's and a bare lookup's.

    The demotion is free: measured on the Gītā padapāṭha it changes nothing — 38.5% overall, 33.6%
    nouns, 26.6% verbs, identical either way — because the model's whole contribution is to NOUNS
    (+11.7pt), and it never helped verbs, where the Dhātupāṭha and the gaṇa preference already do
    the work. Removing a known failure mode at zero measured cost needs no further argument.
    """
    if not any(s.source.startswith("dhatupatha") for s in senses):
        return senses
    llm = [s for s in senses if s.source == "llm"]
    if not llm:
        return senses
    return [s for s in senses if s.source != "llm"] + llm


def _prefer_matching_gana(senses: list[Sense], analysis) -> list[Sense]:
    """Put the root the analysis actually identified first.

    Homonymous roots are ordinary in Sanskrit — `kṛ` is svādi *hiṃsāyām* "to kill" AND tanādi
    *karaṇe* "to do" — and the Dhātupāṭha lists both with no way to choose. But the morphology
    already resolved it: the inflected form came from one specific dhātu with one specific gaṇa.
    Reordering on that is precise, and needs no frequency data or guesswork.
    """
    gana = (analysis.features or {}).get("gana")
    if not gana or len(senses) < 2:
        return senses
    matching = [s for s in senses if s.source.startswith("dhatupatha") and gana in s.gloss]
    if not matching:
        return senses
    return matching + [s for s in senses if s not in matching]


def _prefer_matching_gender(senses: list[Sense], analysis) -> list[Sense]:
    """Put senses whose gender matches the form's gender first.

    The nominal counterpart of `_prefer_matching_gana`, and for the same reason. Homonymous
    nominal stems are ordinary in Sanskrit and they differ in gender: MW records that per sense
    (m. 63,888, mfn. 50,738, n. 33,666, f. 31,341 — 62.7% of entries), and the morphology has
    already resolved which gender the inflected form actually is. Matching the two needs no
    frequency data and no guessing, exactly like the gaṇa case, which measured +19.5pt on the
    verbs where it fires.

    `mfn.` is recorded as "any": it marks an ADJECTIVAL sense, which takes the gender of whatever
    it qualifies, so it must never be demoted for disagreeing — it agrees by definition.
    Senses with no recorded gender are left where they are rather than pushed down; an unmarked
    sense is unknown, not wrong.

    MEASURED AND NOT WIRED IN. On the 1,969 Gītā nouns where this changes the order it scores
    19.5% against 26.9% without — **-7.5pt** — where the identical idea applied to verbs via gaṇa
    gains +19.5pt. The asymmetry is in the INPUT, not the principle: a verb's gaṇa comes from the
    dhātu the morphology positively identified, while a noun's gender is a selection we get right
    only about 72-90% of the time. Filtering good senses through a feature that is itself often
    wrong subtracts more than it adds. This becomes viable when gender accuracy rises; the column
    it needs is already populated.
    """
    want = (analysis.features or {}).get("gender")
    if not want or len(senses) < 2:
        return senses
    matching = [s for s in senses if s.gender in (want, "any")]
    if not matching or len(matching) == len(senses):
        return senses
    rest = [s for s in senses if s not in matching]
    return matching + rest


def senses_for(analysis) -> list[Sense]:
    """Every sense the engine would SHOW for one analysed word, in the order it would show them.

    This is the single definition of "what the reader sees", and both the pipeline and the
    evaluations go through it. They used not to: `evals/sense_ranking.py` scored raw rows straight
    out of the `sense` table, which skips deduplication, the gaṇa preference and the curated
    particle glosses. It reported consensus ranking at +1.2pt when the real path gives -5.5pt and
    0 of 18 chapters improved — a comparison that was exactly backwards, because the particles
    whose curated glosses collapse 39.0% -> 10.8% under that ranking were invisible to it.

    Anything that measures sense quality must call this, never `SELECT ... FROM sense`.
    """
    from core.morphology import PARTICLES, UPASARGAS
    if analysis is None:
        return []
    if analysis.pos == "upasarga":
        return [Sense(source="upasarga",
                      gloss=f"{UPASARGAS[analysis.lemma]} (verbal prefix)")]
    if analysis.pos == "particle":
        # MW lists `na` as "the dental nasal"; the particle's own gloss is what a reader needs.
        # Avyayas identified from the lexicon rather than the hand list have no curated gloss,
        # so they fall through to ordinary lookup.
        gloss = PARTICLES.get(analysis.lemma)
        return [Sense(source="particle", gloss=gloss)] if gloss else lookup(analysis.lemma)
    return _prefer_matching_gana(lookup(analysis.lemma), analysis)


def attach_senses(result: ParseResult) -> ParseResult:
    """Fill each token's `.senses` from the dictionary (mutates and returns the result)."""
    for token in result.tokens:
        if token.analysis is not None:
            token.senses = senses_for(token.analysis)
    return result


if __name__ == "__main__":
    build_db()
    for w in ("jala", "SUnya", "Atman", "gam"):
        print(f"{w}: {[s.gloss for s in lookup(w)]}")
