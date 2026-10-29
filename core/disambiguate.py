# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 3 — minimal syntactic disambiguation for simple clauses.

Per-word morphology is ambiguous: a neuter noun like `jala` is both nominative and accusative,
so *which* reading is right depends on the sentence. This is a small, deterministic simple-clause
rule:

  • the finite verb is fixed;
  • one subject = the unambiguous nominative (else the leftmost nominative-capable token);
  • any other nominative/accusative-ambiguous nominal defaults to the object (accusative).

Correct for simple transitive clauses and fully deterministic. Real context-aware disambiguation
(retrieval-assisted, handling complex sentences) is a later phase — this just makes the core sound
and reproducible on the clauses it targets today.
"""
from __future__ import annotations

from .models import Analysis


from functools import lru_cache


@lru_cache(maxsize=1)
def _valency() -> dict[str, float]:
    """Median object count per verb lemma, learned from DCS (see knowledge/ingest_valency.py)."""
    try:
        from knowledge.ingest_valency import load
        return load()
    except Exception:                              # noqa: BLE001 — the prior is optional
        return {}


#: How far to trust the learned valency prior — MEASURED, not assumed.
#:
#: The tempting restriction is to believe the prior only when it says a verb takes NO object, on
#: the reasoning that akarmaka is a hard fact about the root (`bhū`, `as`, `sthā` cannot govern a
#: karma at all) while "one object" or "two" is contextual and a median cannot express that `kṛ`
#: governs 0, 1 or 2 by sentence. A prior that only ever SUPPRESSES impossible objects would make
#: only claims its evidence supports.
#:
#: It is worse. Held-out case accuracy:
#:
#:      policy        vedic    kavya   upanisad
#:      all           61.3%    69.4%     68.8%
#:      zero_only     61.0%    69.0%     68.2%
#:
#: So the signal is not concentrated in the intransitives. Suppressing objects for akarmaka verbs
#: gains less than the dvikarmaka counts contribute, and restricting the prior loses ground in
#: every band. Kept as a switch because the reasoning is worth preserving beside the refutation.
_VALENCY_POLICY = "all"


def _karma_count(known: list[float]) -> int:
    """How many karma slots the verb(s) of this clause license."""
    high = max(known)
    if _VALENCY_POLICY == "all":
        return int(round(high))
    if _VALENCY_POLICY == "zero_only":
        return 0 if high < 0.5 else 1        # only ever suppress, never add
    return int(round(high))


def _noun_cases(cands: list[Analysis]) -> set[str]:
    return {c.features.get("case", "") for c in cands if c.pos == "noun"}


#: NUMBER MARKEDNESS. Pāṇini 1.4.22 `dvyekayor dvivacanaikavacane` — the dual is used for exactly
#: two, the singular for exactly one. The dual therefore makes a positive semantic claim and has to
#: be LICENSED; it is never what you fall back to when nothing decided the token.
#:
#: This matters because `-e` is systematically ambiguous on a-stems: `arthe` is locative SINGULAR
#: ("in the matter") or accusative/nominative DUAL ("two matters"), and the two readings are
#: identical in form. The same holds for `tantre`, `divase`, `āloke`, `phale`.
_NUMBER_MARKEDNESS = {"singular": 0, "plural": 1, "dual": 2}


def _least_marked(cands: list[Analysis]) -> Analysis | None:
    """The noun reading making the weakest claim about number. Candidate order breaks ties."""
    nouns = [c for c in cands if c.pos == "noun"]
    if not nouns:
        return None
    return min(nouns, key=lambda c: _NUMBER_MARKEDNESS.get(c.features.get("number", ""), 3))



def _nominative_costs_a_dual(cands: list[Analysis]) -> bool:
    """Would choosing nominative here force us to assert the dual, when a singular is available?

    On a-stems `-e` fills nominative/accusative DUAL and locative SINGULAR alike. Preferring
    nominative unconditionally therefore buys the case at the price of claiming "exactly two",
    which 1.4.22 says is a positive semantic claim. When some other case offers a singular, that
    is the weaker and safer reading.
    """
    nom = [c for c in cands if c.pos == "noun" and c.features.get("case") == "nominative"]
    if not nom or any(c.features.get("number") != "dual" for c in nom):
        return False
    return any(c.pos == "noun" and c.features.get("case") != "nominative"
               and c.features.get("number") == "singular" for c in cands)


def select(candidate_lists: list[list[Analysis]]) -> list[Analysis]:
    """Choose one Analysis per token from its deterministic candidate list."""
    n = len(candidate_lists)
    chosen: list[Analysis | None] = [None] * n
    verbal = [False] * n

    # 1. Finite verbs — ZERO, ONE OR SEVERAL. Committing to exactly one verb per sentence was
    #    wrong in both directions, and the numbers say the damage is mostly over-production:
    #    against DCS's finite verbs we scored precision 73.7% / recall 90.7%, inventing a verb
    #    3.5x more often than missing one. **68% of real sentences have no finite verb at all** —
    #    Sanskrit drops the copula and sastra prose is largely definitional — while only 2.9% have
    #    two or more. So "none" must be an available answer, and "several" an allowed one.
    #
    #    A verb reading is credible when nothing nominal competes with it, or when it is third
    #    person — the declarative default. `rAmas` parses as √rā 1st-person PLURAL beside a clean
    #    nominative noun, and is a noun; `vidyate` is a clean 3rd-person singular, and is a verb.
    #
    #    Measured: verb F1 81.4% -> 89.9%, case 71.0% -> 73.0%, gender 66.8% -> 68.1%, karaka 20/20.
    #    (Non-finite forms are deliberately NOT verbs here: krdanta take case endings and are
    #    nominals in Paninian terms, whatever UD's UPOS calls them.)
    def _best_verb_reading(cands: list[Analysis]) -> Analysis | None:
        verbs = [c for c in cands if c.pos == "verb"]
        if not verbs:
            return None
        return min(verbs, key=lambda v: (0 if v.features.get("person") == "third" else 1,
                                         0 if v.features.get("number") != "dual" else 1))

    for i, cands in enumerate(candidate_lists):
        verb = _best_verb_reading(cands)
        if verb is None:
            continue
        competing_noun = any(c.pos == "noun" for c in cands)
        if not competing_noun or verb.features.get("person") == "third":
            chosen[i] = verb
            verbal[i] = True

    # 2. Pick the subject: prefer an unambiguous nominative, else the leftmost nominative-capable —
    #    but first narrow to nominals that AGREE WITH THE VERB IN NUMBER. That is a Pāṇinian
    #    constraint, not a heuristic: the kartā and the tiṅanta share vacana, so a plural nominal
    #    cannot be the subject of a singular verb. Worth +0.8pt of number accuracy.
    #
    #    Note this step is nearly vestigial for CASE: since non-subject nominals default to
    #    nominative anyway, removing subject selection outright moves 0.62% of tokens and 0.0pt of
    #    case accuracy. It earns its place by disambiguating number, not by finding "the" subject —
    #    Sanskrit sentences routinely have several nominatives and this does not pretend otherwise.
    verb_number = next((chosen[i].features.get("number") for i in range(n) if verbal[i]), None)
    nominal_idx = [i for i in range(n) if not verbal[i] and any(c.pos == "noun" for c in candidate_lists[i])]
    nom_capable = [i for i in nominal_idx if "nominative" in _noun_cases(candidate_lists[i])]
    if verb_number:
        agreeing = [i for i in nom_capable
                    if verb_number in {c.features.get("number") for c in candidate_lists[i]
                                       if c.pos == "noun" and c.features.get("case") == "nominative"}]
        # No fallback. If NOTHING agrees with the verb in vacana, the sentence has no overt
        # subject — and that is ordinary Sanskrit, not a failure: 3.4.69 has the tiṅ ending itself
        # express the kartā, so a nominative word is optional. `nyāye arthe vartate` has a singular
        # verb and two words whose only nominative reading is DUAL; forcing one of them to be the
        # subject buys a nominative by asserting "exactly two" (1.4.22), and then the other is
        # dragged along too. Both are simply locative singulars, and the agent is in `-te`.
        nom_capable = agreeing
    only_nom = [i for i in nom_capable if _noun_cases(candidate_lists[i]) == {"nominative"}]
    subject = only_nom[0] if only_nom else (nom_capable[0] if nom_capable else None)

    # 3. Assign each nominal's case. A clause has ONE direct object, not N-1 of them.
    #    Defaulting every non-subject to accusative over-produced it 2.4x against DCS — 1440
    #    nominatives read as accusative, the single largest error cell — because the "one subject,
    #    rest are objects" assumption does not hold: 58% of real sentences carry MORE THAN ONE
    #    nominative. Sastra prose is largely definitional ("X is Y"), and Sanskrit drops the copula,
    #    so a verbless sentence has no karma to fill at all.
    #    The karma candidate is the nominal nearest the verb — Sanskrit is verb-final, so that is
    #    the last non-subject nominal. Every other nominal prefers nominative.
    #    Worth +14.4pt of case accuracy (56.6% -> 71.0%) with karaka held at 20/20 on the gold set;
    #    it also lifts gender, which is capped by case (83.6% correct when case is right, 32.5%
    #    when it is wrong).
    #    KARMA IS THE RESIDUAL ROLE. Pāṇini defines it three times, and the third is the one that
    #    decides this: 1.4.49 kartur īpsitatamaṃ karma (what the agent most seeks to reach),
    #    1.4.50 tathāyuktaṃ cānīpsitam (what is similarly connected though undesired), and
    #    **1.4.51 akathitaṃ ca — "and what is NOT STATED otherwise."** Akathita is the whole
    #    point: once the roles with positive definitions are assigned, whatever participant is
    #    left over is karma. It is the DEFAULT, not a single privileged slot — which is why the
    #    grammar can license two accusatives at all (gāṃ dogdhi payaḥ, māṇavakaṃ panthānaṃ
    #    pṛcchati; the dvikarmaka list duh-yāc-pac-daṇḍ-rudh-pracch-ci-brū-śās-jñā-manth-muṣ).
    #
    #    This code had the logic exactly inverted. It allowed ONE karma — the nominal nearest the
    #    verb — and defaulted everything else to nominative. That was fitted to DCS śāstra prose
    #    for +14.4pt and written in beside real sūtra citations, which is the actual mistake: it
    #    is not a rule of Sanskrit. On `cakṣuḥ śrotraṃ kaḥ u devaḥ yunakti` ("which god yokes the
    #    eye and the ear?") it flattens one of two objects to nominative.
    #
    #    Measured before changing anything: of the accusatives we get wrong, 86-91% are forms
    #    genuinely ambiguous between nominative and accusative, and ZERO are unambiguous forms
    #    being overwritten. So the fix has to be the default, not a guard. Accusative recall was
    #    30% on the Kena, 43% on the Nāṭyaśāstra, 0/7 on the Nyāyasūtra — the inversion was
    #    never genre-specific, it was hidden inside a healthy-looking average because nominatives
    #    are numerous and we over-assigned them.
    #
    #    TWO GATES keep this honest, and both are grammatical rather than defensive:
    #
    #      * no finite verb -> no karma at all. 1.4.49 says *kartuḥ* — karma presupposes an agent
    #        performing a kriyā. A verbless sentence is predication, not action: `śrotrasya
    #        śrotram manaso manaḥ` is "the ear of the ear, the mind of the mind", all nominative.
    #      * kartā not identified -> do not invert. If agreement could not settle who acts,
    #        declaring every remaining nominal an object would leave the clause with no agent,
    #        which is worse than the error being fixed. Fall back to nominative and say so.
    #
    #    An UNAMBIGUOUS nominative is never touched by any of this: the inversion can only choose
    #    accusative where the form actually permits it, so coordinated agents stay agents.
    #    MEASURED AND REVERTED: applying akathitaṃ ca as a blanket default made every band WORSE
    #    (upaniṣad 64.7->62.9, śāstra 74.2->73.1, sūtra 84.5->83.8) and merely flipped the
    #    dominant error from acc->nom 19.6% to nom->acc 20.2%. The sūtra is right; a global
    #    default is the wrong way to apply it. "Not stated otherwise" presupposes the OTHER kārakas
    #    have been assigned semantically (1.4.23-48), which a surface-case reading cannot do — and
    #    58% of real sentences carry more than one nominative, so most ambiguous nominals in a
    #    verbed clause are genuinely nominative (predicate nominatives, coordinated agents,
    #    apposition). Neither "one karma, rest nominative" nor "one kartā, rest karma" is a rule of
    #    Sanskrit; the deciding signal is the VERB'S VALENCY, not a default. See BACKLOG.
    #    HOW MANY OBJECTS? Until now this was hardcoded to one, which is not a rule of Sanskrit —
    #    1.4.51 akathitaṃ ca licenses as many karmas as there are unassigned participants, and the
    #    vārttika on it names the dvikarmaka roots outright. The count is a property of the VERB.
    #
    #    Pāṇini states the category (3.4.69 turns on sakarmaka vs akarmaka) but no machine-readable
    #    source we have carries it: vidyut's `karmatva` is None for all 45,395 dhātus. So it is
    #    estimated from annotation, held out across registers, and checked against the grammar —
    #    the estimate independently recovers the dvikarmaka class (brū 2, dā 2, jñā 2) and puts
    #    as/bhū/sthā at 0. Verbs with no prior keep the old single-karma behaviour, so an unknown
    #    verb is never made worse than before.
    has_verb = any(verbal)
    non_subject = [i for i in nominal_idx if i != subject]
    n_karma = 1
    if has_verb:
        prior = _valency()
        lemmas = [chosen[i].lemma.split("#")[0] for i in range(n) if verbal[i] and chosen[i]]
        known = [prior[l] for l in lemmas if l in prior]
        if known:
            n_karma = _karma_count(known)
    #    Objects sit nearest the verb — Sanskrit is verb-final — so fill from the end.
    karma_idx = set(non_subject[-n_karma:]) if (has_verb and non_subject and n_karma > 0) else set()
    karma = None                                   # kept for the single-slot branch below
    for i in nominal_idx:
        avail = _noun_cases(candidate_lists[i])
        if i == subject and "nominative" in avail:
            target = "nominative"
        elif i in karma_idx and "accusative" in avail:
            target = "accusative"
        elif "nominative" in avail and not _nominative_costs_a_dual(candidate_lists[i]):
            target = "nominative"
        elif avail:
            # Nothing assigned this token a role. The old chain took ACCUSATIVE here
            # unconditionally, which is a fixed case preference wearing no grammatical clothes —
            # and on `-e` forms it silently chose accusative-DUAL over locative-SINGULAR, because
            # "accusative" was simply checked first. Measured, that single line was the dominant
            # number error in every band we have: singular read as dual, 8.0% of Vedic tokens,
            # 7.6% of kāvya, 6.1% of sūtra — the same defect the sūtra band reports from the other
            # side as loc->nom.
            #
            # Choose by markedness instead (1.4.22): assert the weakest number the form permits,
            # and let the deterministic candidate order settle what remains.
            best = _least_marked(candidate_lists[i])
            target = best.features.get("case") if best else sorted(c for c in avail if c)[0]
        else:
            target = None
        matching = [c for c in candidate_lists[i]
                    if c.pos == "noun" and c.features.get("case") == target]
        # among equally-cased readings, a nominative agreeing with the verb's number wins
        if verb_number and target == "nominative":
            matching = [c for c in matching if c.features.get("number") == verb_number] or matching
        chosen[i] = matching[0] if matching else candidate_lists[i][0]

    # 4. Anything still unassigned (pos "other"/"unknown"): take the first deterministic candidate.
    for i in range(n):
        if chosen[i] is None:
            chosen[i] = candidate_lists[i][0]
    return chosen  # type: ignore[return-value]
