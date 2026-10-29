# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Sandhi round-trip sieve — rules out splits that could not have produced the surface text.

Sandhi *joining* is deterministic even though *splitting* is ambiguous, so a proposed segmentation
can be checked by rejoining it under Paninian rules and asking whether it reproduces the original.

What this does and does not buy us, measured rather than assumed:

  * It rules OUT.  A split that cannot rejoin is provably wrong, with no ground truth involved.
  * It does NOT rule in.  Both `sadgam+aya` and the correct `sat+gamaya` rejoin validly — splitting
    is ambiguous precisely because several splits are phonologically legal.  This is a sieve that
    shrinks the candidate set; picking among survivors needs lexical knowledge, not phonology.

One trap it took a wrong prototype to find: validity is NOT chunk-local.  `nABAvo` has a final `-o`
(from `-as`) that only arises before the *next* word, so a chunk checked in isolation fails even
when correct.  Joining therefore folds across the whole line, carrying context.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

_RULES = Path(__file__).resolve().parent.parent / "vidyut-data" / "sandhi" / "rules.csv"

# The `result` column marks the surviving word boundary with a space ("t","g" -> "d g"); we compare
# against space-free text, so strip it. Losing that mark costs nothing for a validity check.
_MAX_FIRST = 0


@lru_cache(maxsize=1)
def _joiner() -> dict[tuple[str, str], frozenset[str]]:
    global _MAX_FIRST
    table: dict[tuple[str, str], set[str]] = defaultdict(set)
    with _RULES.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            first, second = row["first"], row["second"]
            if not first:
                continue
            table[(first, second)].add(row["result"].replace(" ", ""))
            _MAX_FIRST = max(_MAX_FIRST, len(first))
    return {k: frozenset(v) for k, v in table.items()}


def joins(a: str, b: str) -> set[str]:
    """Every surface string `a` and `b` could produce under some sandhi rule (plus concatenation)."""
    table = _joiner()
    out = {a + b}                                    # no sandhi applies / already resolved
    for cut in range(1, min(_MAX_FIRST, len(a)) + 1):
        stem, first = a[:-cut], a[-cut:]
        for (f, s), results in table.items():
            if f != first or not b.startswith(s):
                continue
            tail = b[len(s):]
            out.update(stem + res + tail for res in results)
    return out


def validate(parts: list[str], surface: str) -> bool:
    """Could `parts` have produced `surface`? Folds left across the whole line, keeping context.

    States are pruned to those still a prefix of the target, which keeps the search small despite
    each boundary being individually ambiguous.
    """
    target = surface.replace(" ", "")
    if not parts:
        return not target
    _joiner()                                        # populates _MAX_FIRST
    states = {parts[0]}
    for part in parts[1:]:
        nxt = {s for state in states for s in joins(state, part)}
        # A state is viable if its *settled* prefix matches the target. The trailing _MAX_FIRST
        # characters are NOT settled: a later join can still rewrite them (nABAvas + hi -> nABAvohi
        # rewrites `as` to `o`), so pruning on the full string would discard correct paths.
        states = {s for s in nxt if target.startswith(s[:max(0, len(s) - _MAX_FIRST)])}
        if not states:
            return False
    return target in states


if __name__ == "__main__":
    for parts, surface, note in [
        (["sat", "gamaya"], "sadgamaya", "correct"),
        (["sadgam", "aya"], "sadgamaya", "engine's wrong split"),
        (["na", "aBAvas", "hi"], "nABAvo hi", "needs next-word context"),
        (["nAs", "BAvas", "hi"], "nABAvo hi", "engine's wrong split"),
        (["tat", "tvam", "asi"], "tattvamasi", "correct"),
        (["jalam", "pibati"], "jalampibati", "no sandhi"),
        (["xyz", "abc"], "sadgamaya", "nonsense"),
    ]:
        print(f"  {validate(parts, surface)!s:5s}  {'+'.join(parts):22s} -> {surface:14s} ({note})")
