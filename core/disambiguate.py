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


def _noun_cases(cands: list[Analysis]) -> set[str]:
    return {c.features.get("case", "") for c in cands if c.pos == "noun"}


def select(candidate_lists: list[list[Analysis]]) -> list[Analysis]:
    """Choose one Analysis per token from its deterministic candidate list."""
    n = len(candidate_lists)
    chosen: list[Analysis | None] = [None] * n
    verbal = [False] * n

    # 1. The finite verb = the LAST verb-capable token (simple clauses are verb-final).
    #    A noun surface can carry a spurious verb reading (e.g. rāmas), so we don't mark every
    #    verb-capable token as the verb — only the clause-final one; the rest fall back to nouns.
    verb_capable = [i for i, cands in enumerate(candidate_lists) if any(c.pos == "verb" for c in cands)]
    if verb_capable:
        vi = verb_capable[-1]
        chosen[vi] = next(c for c in candidate_lists[vi] if c.pos == "verb")
        verbal[vi] = True

    # 2. Pick the subject: prefer an unambiguous nominative, else the leftmost nominative-capable.
    nominal_idx = [i for i in range(n) if not verbal[i] and any(c.pos == "noun" for c in candidate_lists[i])]
    nom_capable = [i for i in nominal_idx if "nominative" in _noun_cases(candidate_lists[i])]
    only_nom = [i for i in nom_capable if _noun_cases(candidate_lists[i]) == {"nominative"}]
    subject = only_nom[0] if only_nom else (nom_capable[0] if nom_capable else None)

    # 3. Assign each nominal's case: subject → nominative; ambiguous others → accusative (object).
    for i in nominal_idx:
        avail = _noun_cases(candidate_lists[i])
        if i == subject and "nominative" in avail:
            target = "nominative"
        elif "accusative" in avail:
            target = "accusative"
        elif avail:
            target = sorted(c for c in avail if c)[0]
        else:
            target = None
        chosen[i] = next(
            (c for c in candidate_lists[i] if c.pos == "noun" and c.features.get("case") == target),
            candidate_lists[i][0],
        )

    # 4. Anything still unassigned (pos "other"/"unknown"): take the first deterministic candidate.
    for i in range(n):
        if chosen[i] is None:
            chosen[i] = candidate_lists[i][0]
    return chosen  # type: ignore[return-value]
