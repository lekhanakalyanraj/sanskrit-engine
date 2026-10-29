# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 4 — deterministic kāraka graph.

A Phase-1 simplification: map each nominal's vibhakti (case) to its kāraka role, and attach
every argument to the (single) finite verb. Correct for simple sentences; the case→role map is
not 1:1 in the general case — that ambiguity is what a later disambiguation layer handles.
"""
from __future__ import annotations

from functools import lru_cache

from .models import KarakaEdge, Token

# kāraka role → its usual English names (used when explaining, and by the verifier so an English
# role word in a reading isn't mistaken for invented content)
KARAKA_ENGLISH: dict[str, str] = {
    "kartā": "agent doer subject",
    "karma": "object patient goal",
    "karaṇa": "instrument means",
    "sampradāna": "recipient beneficiary",
    "apādāna": "source origin",
    "adhikaraṇa": "locus location place",
    "sambandha": "of relation belonging possession",
    "viśeṣaṇa": "qualifying describing attribute",
}

# Vibhakti → kāraka is NOT one fixed table: it depends on the verb's prayoga (voice). Pāṇini
# assigns the cases by rule, and the two voices assign them differently:
#
#   kartari (active)   kartā → prathamā (nom.)      karma → dvitīyā (acc.)
#   karmaṇi (passive)  karma → prathamā (nom.)      kartā → tṛtīyā (instr.)   [2.3.18]
#
# We previously hardcoded the active table, so on every passive sentence the agent and the object
# were exchanged — `ucyate`, `kriyate`, `vidyate` are ordinary śāstra vocabulary, and 11.5% of the
# verbed sentences in our DCS sample are unambiguously passive. That is not a mislabelling; it
# reverses who does what to whom, which is the one thing a reading must not get wrong.
CASE_TO_KARAKA_ACTIVE: dict[str, str] = {
    "nominative": "kartā",      # agent
    "accusative": "karma",      # object
    "instrumental": "karaṇa",   # instrument
    "dative": "sampradāna",     # recipient
    "ablative": "apādāna",      # source
    "locative": "adhikaraṇa",   # locus
    # genitive (sambandha) and vocative are not core kārakas — 2.3.50 śeṣe ṣaṣṭhī
}

CASE_TO_KARAKA_PASSIVE: dict[str, str] = {
    **CASE_TO_KARAKA_ACTIVE,
    "nominative": "karma",      # what the active voice would have made the object
    "instrumental": "kartā",    # 2.3.18 kartṛkaraṇayos tṛtīyā — see the note in build_karaka_edges
}

#: kept for callers that want the plain active table
CASE_TO_KARAKA = CASE_TO_KARAKA_ACTIVE


#: How far ahead a qualifier's noun sits, measured on 1,006 gold links: 74.5% immediately after,
#: 93.9% within two, 97.9% within three. Beyond that the gain is noise and the false positives are
#: not, so the window stops at three.
_VISESANA_WINDOW = 3


@lru_cache(maxsize=1)
def _qualificative() -> frozenset[str]:
    """Lemmas the lexicographers mark `mfn.` / `a.` — see knowledge/ingest_adjectives.py."""
    import sqlite3
    from pathlib import Path
    db = Path(__file__).resolve().parent.parent / "knowledge" / "sanskrit.db"
    if not db.exists():
        return frozenset()
    conn = sqlite3.connect(db)
    try:
        return frozenset(r[0] for r in conn.execute("SELECT lemma FROM adjective"))
    except sqlite3.Error:
        return frozenset()
    finally:
        conn.close()


def _agrees(a: Token, b: Token) -> bool:
    """Sāmānādhikaraṇya — a common substrate. Same case, gender AND number is the definition of
    the viśeṣaṇa relation, not an approximation of it."""
    if not (a.analysis and b.analysis):
        return False
    fa, fb = a.analysis.features, b.analysis.features
    keys = ("case", "gender", "number")
    return all(fa.get(k) and fa.get(k) == fb.get(k) for k in keys)


def _visesana_edges(tokens: list[Token]) -> list[KarakaEdge]:
    """Qualifier → qualified, for nominals sharing case, gender and number.

    Direction is settled by word order, which measured 97.1% on 801 gold links — far above every
    morphological signal tried (declared lingas 58.4%, derivation 39.3%, lexical marking 65.9%).
    Sanskrit's free word order governs clause constituents; inside a nominal phrase the qualifier
    conventionally comes first.

    The lexicographers' mark is used as a FILTER on the candidate qualifier, not as the decider —
    it carries 96% of real adjectives but also 38% of nouns, so it narrows the field and cannot
    choose within it.
    """
    marked = _qualificative()
    nominals = [t for t in tokens if t.analysis and t.analysis.pos == "noun"]
    edges: list[KarakaEdge] = []
    taken: set[int] = set()
    for i, dep in enumerate(nominals):
        if dep.id in taken:
            continue
        lemma = (dep.analysis.lemma or "").split("#")[0]
        if marked and lemma not in marked:
            continue                                   # not recorded as qualificative
        for head in nominals[i + 1:i + 1 + _VISESANA_WINDOW]:
            if _agrees(dep, head):
                edges.append(KarakaEdge(head=head.id, dependent=dep.id, role="viśeṣaṇa"))
                taken.add(dep.id)
                break
    return edges


def _governing_verb(token: Token, verbs: list[Token]) -> Token | None:
    """The verb whose action this nominal participates in.

    A kāraka is defined relative to a kriyā (1.4.23), so in a sentence with several finite verbs
    each argument belongs to *its own* verb — we previously attached everything to the first one.

    Sanskrit clauses are verb-final, so a nominal's verb is normally the next one to its right;
    only when nothing follows does it look left. Where that leaves a choice for a nominative, the
    Pāṇinian agreement constraint decides it: the kartā shares vacana with its verb.
    """
    if not verbs:
        return None
    after = [v for v in verbs if v.id > token.id]
    before = [v for v in verbs if v.id < token.id]
    pool = after or before
    if not pool:
        return None
    if token.analysis and token.analysis.features.get("case") == "nominative":
        number = token.analysis.features.get("number")
        agreeing = [v for v in pool if v.analysis and v.analysis.features.get("number") == number]
        if agreeing:
            return agreeing[0] if pool is after else agreeing[-1]
    return pool[0] if pool is after else pool[-1]


def _sambandha_head(token: Token, nominals: list[Token]) -> Token | None:
    """What a genitive qualifies. 2.3.50 śeṣe ṣaṣṭhī — the sixth case covers the *remainder*:
    relations that are not kārakas at all, so the head is another NOMINAL, never the verb.
    Sanskrit places the genitive before what it qualifies (`rāmasya putraḥ`), so look right first.
    """
    after = [o for o in nominals
             if o.id > token.id and o.analysis.features.get("case") != "genitive"]
    if after:
        return after[0]
    before = [o for o in nominals
              if o.id < token.id and o.analysis.features.get("case") != "genitive"]
    return before[-1] if before else None


def build_karaka_edges(tokens: list[Token]) -> list[KarakaEdge]:
    """Each nominal's vibhakti → its kāraka role, under the voice of *its own* verb.

    Known limitation, recorded rather than guessed at: tṛtīyā expresses BOTH kartā and karaṇa
    (2.3.18), so in the passive an instrumental is genuinely ambiguous between "by whom" and "by
    what". Sanskrit resolves it by animacy, which we do not have. The first instrumental of a clause
    is taken as the agent and the rest as instruments — where several compete, that first one is a
    guess the grammar does not license.
    """
    verbs = [t for t in tokens if t.analysis and t.analysis.pos == "verb"]
    nominals = [t for t in tokens if t.analysis and t.analysis.pos == "noun"]
    edges: list[KarakaEdge] = []
    agent_taken: set[int] = set()          # per verb, not per sentence

    for token in nominals:
        case = token.analysis.features.get("case", "")

        if case == "genitive":             # not a kāraka; relates to a nominal
            head = _sambandha_head(token, nominals)
            if head is not None:
                edges.append(KarakaEdge(head=head.id, dependent=token.id, role="sambandha"))
            continue

        verb = _governing_verb(token, verbs)
        if verb is None:
            continue
        passive = verb.analysis.features.get("voice") == "passive"
        role = (CASE_TO_KARAKA_PASSIVE if passive else CASE_TO_KARAKA_ACTIVE).get(case)
        if passive and case == "instrumental":
            role = "karaṇa" if verb.id in agent_taken else "kartā"
            agent_taken.add(verb.id)
        if role:
            edges.append(KarakaEdge(head=verb.id, dependent=token.id, role=role))

    # viśeṣaṇa detection is BUILT (see `_visesana_edges`) and deliberately NOT wired in. Measured
    # against 2,582 gold links it reaches 30.8% recall at 38% precision — 48% even restricted to
    # adjacent pairs — and it cost 493 correct kartā edges, dropping that role from 48.8% to 40.9%.
    #
    # Over half the relations it emits would be false, and a false relation is a claim about
    # meaning: "this word describes that one" is worse than silence for a reader. The cap is not
    # the window or the filter — agreement needs case, gender AND number correct on BOTH words, and
    # case alone is 74%, so precision cannot exceed the accuracy it depends on.
    #
    # Kept rather than deleted because the machinery is right and the measurement is recorded: when
    # case selection improves, this becomes viable without being rebuilt.
    return sorted(edges, key=lambda e: e.dependent)
