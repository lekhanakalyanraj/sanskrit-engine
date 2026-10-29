# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Human curation layer over the dictionary.

The MW cleaner is heuristic, so some glosses are still junk and some good senses are missing. This
records human judgements — hide / edit / add — and applies them on top of the generated data.

**Curation lives in its own YAML file, not in the database**, because re-ingesting MW deletes and
rebuilds every `source='MW'` row; anything stored there would be destroyed on the next ingest.
`curation.yaml` is hand-readable, diffable, and is a genuine asset — the same reasoning as the
gold set (CC-BY-SA), so it is worth committing.

    from knowledge.curation import add_rule, load_rules, apply_rules, suspicion_flags
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.models import Sense

_FILE = Path(__file__).resolve().parent / "curation.yaml"
_CACHE: dict[str, list[dict]] | None = None

HIDE, EDIT, ADD, FLAG, REVIEWED = "hide", "edit", "add", "flag", "reviewed"


# ── suspicion heuristics — how we surface likely-bad data for review ──────────
#: Dictionaries written for readers rather than for completeness. Brevity in these is a virtue.
_CONCISE_SOURCES = frozenset({"apte", "macdonell", "seed"})


def _looks_like_words(gloss: str) -> bool:
    """Clean words, not apparatus — "duty" yes, "i, 10" no."""
    tokens = gloss.replace(",", " ").replace(";", " ").split()
    return bool(tokens) and all(t.replace("-", "").isalpha() for t in tokens)


def suspicion_flags(gloss: str, source: str = "MW") -> list[str]:
    """Reasons a gloss looks unclean. Used to prioritise review, never to auto-delete.

    The `source` matters. These heuristics were written when Monier-Williams was the only
    dictionary, and MW is verbose — so a short gloss there usually meant a leftover scrap. Apte and
    Macdonell are the opposite: they are concise ON PURPOSE, and their short glosses are their best
    ones. Flagging "duty", "rule", "right" and "justice" as suspicious sends a curator to review the
    four best readings of `dharma`, which is worse than not flagging at all.
    """
    flags = []
    g = gloss.strip()
    verbose_source = source not in _CONCISE_SOURCES
    # a scrap is short AND malformed — leftover apparatus, not a clean word
    if len(g) < 8 and (verbose_source or not _looks_like_words(g)):
        flags.append("very short")
    if any(ch in g for ch in "{}[]"):
        flags.append("markup residue")
    if g.startswith(("N. of", "Name of")):
        flags.append("proper name")
    if g.startswith("("):
        flags.append("starts mid-parenthesis")
    if "˚" in g or "√" in g:
        flags.append("scholarly shorthand")
    if any(tok in g for tok in ("q.v.", "cf.", "ibid", "&c")):
        flags.append("cross-reference")
    if any(tok in g for tok in ("ifc", "mfn", "Pāṇ.", "Dhātup")):
        flags.append("grammatical apparatus")
    if sum(ch.isdigit() for ch in g) > 3:
        flags.append("citation digits")
    return flags


# ── rule storage ─────────────────────────────────────────────────────────────
def load_rules(force: bool = False) -> dict[str, list[dict]]:
    """All curation rules, keyed by lemma."""
    global _CACHE
    if _CACHE is None or force:
        raw = yaml.safe_load(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
        rules: dict[str, list[dict]] = {}
        for rule in raw or []:
            rules.setdefault(rule["lemma"], []).append(rule)
        _CACHE = rules
    return _CACHE


def _write(rules: dict[str, list[dict]]) -> None:
    flat = [r for group in rules.values() for r in group]
    flat.sort(key=lambda r: (r["lemma"], r.get("action", "")))
    _FILE.write_text(
        "# SPDX-License-Identifier: CC-BY-SA-4.0\n"
        "# Human curation of the dictionary — hide junk, correct glosses, add missing senses.\n"
        "# Applied on top of generated data by knowledge.curation.apply_rules; survives re-ingest.\n"
        + yaml.safe_dump(flat, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    load_rules(force=True)


def add_rule(lemma: str, action: str, *, gloss: str = "", replacement: str = "",
             note: str = "") -> None:
    """Record one judgement. `gloss` identifies the target sense for hide/edit/flag."""
    rules = load_rules()
    entry = {"lemma": lemma, "action": action, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if gloss:
        entry["gloss"] = gloss
    if replacement:
        entry["replacement"] = replacement
    if note:
        entry["note"] = note
    # replace an existing rule for the same lemma+action+target rather than stacking duplicates
    existing = rules.setdefault(lemma, [])
    existing[:] = [r for r in existing
                   if not (r.get("action") == action and r.get("gloss", "") == gloss)]
    existing.append(entry)
    _write(rules)


def remove_rule(lemma: str, action: str, gloss: str = "") -> None:
    rules = load_rules()
    group = rules.get(lemma, [])
    group[:] = [r for r in group if not (r.get("action") == action and r.get("gloss", "") == gloss)]
    if not group:
        rules.pop(lemma, None)
    _write(rules)


# ── applying rules ───────────────────────────────────────────────────────────
def apply_rules(lemma: str, senses: list[Sense]) -> list[Sense]:
    """Apply curation to a lemma's senses: hides removed, edits replaced, additions put first."""
    rules = load_rules().get(lemma)
    if not rules:
        return senses

    hidden = {r["gloss"] for r in rules if r["action"] == HIDE and r.get("gloss")}
    edits = {r["gloss"]: r["replacement"] for r in rules
             if r["action"] == EDIT and r.get("gloss") and r.get("replacement")}

    out: list[Sense] = []
    for rule in rules:                                  # curated additions lead
        if rule["action"] == ADD and rule.get("replacement"):
            out.append(Sense(source="curated", gloss=rule["replacement"]))
    for sense in senses:
        if sense.gloss in hidden:
            continue
        if sense.gloss in edits:
            out.append(Sense(source="curated", gloss=edits[sense.gloss]))
        else:
            out.append(sense)
    return out


def rules_for(lemma: str) -> list[dict]:
    return load_rules().get(lemma, [])


def mark_reviewed(lemma: str, note: str = "") -> None:
    """Record that a human has looked at this lemma — drives review-queue progress."""
    add_rule(lemma, REVIEWED, note=note)


def reviewed_set() -> set[str]:
    return {lemma for lemma, group in load_rules().items()
            if any(r["action"] == REVIEWED for r in group)}


def stats() -> dict:
    rules = load_rules()
    flat = [r for g in rules.values() for r in g]
    return {
        "lemmas_touched": len(rules),
        "rules": len(flat),
        **{a: sum(1 for r in flat if r["action"] == a) for a in (HIDE, EDIT, ADD, FLAG, REVIEWED)},
    }
