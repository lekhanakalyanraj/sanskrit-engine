# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Golden tests for the deterministic core.

Each gold sentence has a hand-verified expected structure; we assert the engine reproduces it
exactly. Because the core is deterministic, these are real assertions — not eval heuristics.

Run:  pytest              (from the sanskrit-engine/ directory, inside the venv)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from core import analyze_sentence
from core.morphology import analyze_candidates, is_valid_word
from core.normalize import to_pausa

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"


def _load_gold() -> list[dict]:
    entries = []
    for path in sorted(GOLD_DIR.glob("*.yaml")):
        for entry in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            entry["_file"] = path.name
            entries.append(entry)
    return entries


GOLD = _load_gold()


def _strip_homonym(lemma: str) -> str:
    """Lexicon marks homonyms as e.g. 'pA#1'; compare on the bare lemma."""
    return re.sub(r"#\d+$", "", lemma)


def test_gold_set_nonempty():
    assert GOLD, "no gold entries found — check gold/*.yaml"


@pytest.mark.parametrize("entry", GOLD, ids=[e["id"] for e in GOLD])
def test_core_matches_gold(entry):
    result = analyze_sentence(entry["sentence_dev"])
    got = result.tokens
    exp = entry["tokens"]

    # 1. Segmentation — exact token sequence
    assert [t.surface_slp1 for t in got] == [tk["slp1"] for tk in exp], "segmentation mismatch"

    # 2. Per-token morphology — lemma, pos, and (for nominals) case
    for g, e in zip(got, exp):
        assert g.analysis is not None, f"no analysis for {g.surface_slp1}"
        assert _strip_homonym(g.analysis.lemma) == e["lemma"], f"lemma mismatch on {e['slp1']}"
        assert g.analysis.pos == e["pos"], f"pos mismatch on {e['slp1']}"
        if "case" in e:
            assert g.analysis.features.get("case") == e["case"], f"case mismatch on {e['slp1']}"

    # 3. Kāraka graph — every expected (dependent, role) edge, and all edges point to the verb
    verb_ids = [t.id for t in got if t.analysis and t.analysis.pos == "verb"]
    assert len(verb_ids) == 1, "expected exactly one finite verb"
    got_edges = {(got[ed.dependent].surface_slp1, ed.role) for ed in result.edges}
    exp_edges = {(tk["slp1"], tk["karaka"]) for tk in exp if "karaka" in tk}
    assert got_edges == exp_edges, "kāraka edge mismatch"
    assert all(ed.head == verb_ids[0] for ed in result.edges), "an edge does not point to the verb"


# ── pausa (written) form vs kosha-facing form ────────────────────────────────────────────────────
# These are two different forms of the same word and conflating them was a live bug: we rendered
# असतस् / भावस्, which no Sanskrit text writes, because the kosha-facing form leaked to display.

@pytest.mark.parametrize("kosha_form, written", [
    ("BAvas", "BAvaH"),      # final s -> visarga
    ("asatas", "asataH"),
    ("punar", "punaH"),      # final r -> visarga too
    ("vidyate", "vidyate"),  # vowel-final: unchanged
    ("jalam", "jalam"),      # final m: unchanged
    ("a", "a"),              # too short to touch
])
def test_to_pausa(kosha_form, written):
    assert to_pausa(kosha_form) == written


def test_display_uses_written_form_lookup_uses_kosha_form():
    """The reader (and the LLM grounding) must see भावः; the lexicon must still get BAvas."""
    result = analyze_sentence("नासतो विद्यते भावः")
    assert [t.surface for t in result.tokens] == ["न", "असतः", "विद्यते", "भावः"]
    assert [t.surface_slp1 for t in result.tokens] == ["na", "asatas", "vidyate", "BAvas"]
    # the kosha rejects the written form outright — which is why the two must stay distinct
    assert is_valid_word("BAvas") and not is_valid_word("BAvaH")


# ── stem gender ──────────────────────────────────────────────────────────────────────────────────
# A nominal stem has an inherent gender (`sTAna` is neuter) which the kosha records on the
# pratipadika. The per-entry linga is only a paradigm slot, and an ending like `-AnAm` fills the
# masculine, neuter and feminine slots alike — so before this, gender fell out of ALPHABETICAL
# order and `sTAnAnAm` came back feminine.

@pytest.mark.parametrize("form, gender", [
    ("sTAnAnAm", "neuter"),       # -AnAm fills all three slots; the stem decides
    ("jYAnAt", "neuter"),
    ("miTyAjYAnAnAm", "neuter"),
    ("apAyAt", "masculine"),
])
def test_stem_gender_ranks_first(form, gender):
    assert analyze_candidates(form)[0].features.get("gender") == gender


def test_stem_gender_does_not_drop_other_readings():
    """Ranking, not filtering — the ambiguity is real and must stay visible to disambiguation."""
    genders = {c.features.get("gender") for c in analyze_candidates("sTAnAnAm")}
    assert {"neuter", "masculine", "feminine"} <= genders


# ── at most one accusative ───────────────────────────────────────────────────────────────────────
# A clause has ONE direct object, not N-1 of them. Defaulting every non-subject nominal to
# accusative over-produced it 2.4x against DCS (1440 nominatives read as accusative) because 58% of
# real sentences carry more than one nominative — sastra prose is largely definitional and Sanskrit
# drops the copula. Worth +14.4pt of case accuracy with karaka unchanged.

def _cases(sentence_dev):
    return [(t.surface_slp1, t.analysis.features.get("case") if t.analysis else None)
            for t in analyze_sentence(sentence_dev).tokens]


@pytest.mark.parametrize("sentence, expected", [
    ("रामः वनम् गच्छति", [("rAmas", "nominative"), ("vanam", "accusative"), ("gacCati", None)]),
    ("मुनिः जलम् पिबति", [("munis", "nominative"), ("jalam", "accusative"), ("pibati", None)]),
])
def test_transitive_clause_keeps_one_accusative(sentence, expected):
    assert _cases(sentence) == expected


def test_only_one_nominal_may_take_accusative():
    """The karma is the nominal nearest the verb; earlier nominals must not all become objects."""
    cases = [c for _, c in _cases("रामः हस्तेन अन्नम् खादति")]
    assert cases.count("accusative") <= 1


# ── zero, one or several finite verbs ────────────────────────────────────────────────────────────
# Committing to exactly one verb per sentence was wrong in both directions. 68% of real sentences
# have NO finite verb (Sanskrit drops the copula; sastra prose is definitional) and 2.9% have two
# or more, so both "none" and "several" must be reachable. `rAmas` parses as √rā 1st-person plural
# beside a clean nominative noun and must stay a noun; `vidyate` is a clean 3rd-person singular.

def _pos(sentence_dev):
    return [(t.surface_slp1, t.analysis.pos) for t in analyze_sentence(sentence_dev).tokens]


def test_verbless_sentence_invents_no_verb():
    """Two nominatives, no copula — the definitional shape that dominates sastra prose."""
    assert _pos("रामः मुनिः") == [("rAmas", "noun"), ("munis", "noun")]


def test_clean_third_person_is_still_a_verb():
    assert _pos("रामः वनम् गच्छति") == [("rAmas", "noun"), ("vanam", "noun"), ("gacCati", "verb")]


def test_spurious_first_person_reading_loses_to_a_nominative():
    """`rAmas` has a √rā 1st-person-plural reading; person is what rules it out, not position."""
    cands = analyze_candidates("rAmas")
    assert any(c.pos == "verb" and c.features.get("person") == "first" for c in cands)
    assert analyze_sentence("रामः मुनिः").tokens[0].analysis.pos == "noun"


# ── prayoga (voice) decides which case carries which kāraka ──────────────────────────────────────
# Pāṇini assigns the cases by rule, and the two voices assign them differently:
#   kartari  kartā → prathamā (nom.)   karma → dvitīyā (acc.)
#   karmaṇi  karma → prathamā (nom.)   kartā → tṛtīyā (instr.)   [2.3.18]
# We hardcoded the active table, so every passive sentence came out with the agent and object
# exchanged — "the rice cooks by means of Rāma". 11.5% of verbed sentences in DCS are passive.

def _roles(sentence_dev):
    r = analyze_sentence(sentence_dev)
    return {r.tokens[e.dependent].surface_slp1: e.role for e in r.edges}


def test_active_voice_nominative_is_the_agent():
    assert _roles("रामः ओदनम् पचति") == {"rAmas": "kartā", "odanam": "karma"}


def test_passive_voice_inverts_agent_and_object():
    """The nominative is what is COOKED; the instrumental is who cooks."""
    assert _roles("रामेण ओदनः पच्यते") == {"rAmeRa": "kartā", "odanas": "karma"}


def test_voice_is_carried_on_the_verb():
    for sentence, want in (("रामः ओदनम् पचति", "active"), ("रामेण ओदनः पच्यते", "passive")):
        verb = next(t for t in analyze_sentence(sentence).tokens
                    if t.analysis and t.analysis.pos == "verb")
        assert verb.analysis.features.get("voice") == want


# ── sambandha: the genitive is not a kāraka ──────────────────────────────────────────────────────
# 2.3.50 śeṣe ṣaṣṭhī — the sixth case covers the *remainder*, relations that are not kārakas, so
# its head is another NOMINAL and never the verb. 5.4% of tokens are genitive and we used to emit
# nothing at all for them: the reader saw the word with no relation shown.

def _edges(sentence_dev):
    r = analyze_sentence(sentence_dev)
    names = {t.id: t.surface_slp1 for t in r.tokens}
    return {(names[e.dependent], e.role, names[e.head]) for e in r.edges}


def test_genitive_attaches_to_a_noun_not_the_verb():
    assert ("rAmasya", "sambandha", "putras") in _edges("रामस्य पुत्रः गच्छति")


def test_genitive_head_is_never_the_verb():
    for dep, role, head in _edges("रामस्य पुत्रः गच्छति"):
        if role == "sambandha":
            assert head != "gacCati"


# ── a kāraka belongs to ITS verb (1.4.23) ────────────────────────────────────────────────────────
# `build_karaka_edges` used to take `next(...)` — the first verb — so in a two-clause sentence every
# nominal was attached to clause one's verb regardless of where it actually belonged.

def test_each_agent_attaches_to_its_own_verb():
    assert _edges("रामः गच्छति मुनिः वदति") == {
        ("rAmas", "kartā", "gacCati"),
        ("munis", "kartā", "vadati"),
    }


# ── avyaya is read from the grammar, not hand-listed ─────────────────────────────────────────────
# An avyaya is never inflected and never fills a kāraka role, so mis-analysing one pollutes the
# semantic graph rather than just the tags. Our hand list covered ~30 words; 541 tokens that DCS
# calls indeclinable were missing, and every one was inflected into a spurious argument.

@pytest.mark.parametrize("word", [
    "tatas",   # -tas taddhita adverb, 5.4.44 ff.
    "atra",    # -tra adverb
    "evam",    # nipāta, 1.1.37 svarādinipātam avyayam
    "iha",
])
def test_indeclinables_are_never_inflected(word):
    cands = analyze_candidates(word)
    assert cands[0].pos == "particle"
    assert "case" not in cands[0].features


def test_indeclinable_takes_no_karaka_role():
    """`tatas` ('thence') must not become an argument of the verb."""
    roles = {t.surface_slp1 for t in analyze_sentence("ततः रामः गच्छति").tokens}
    edges = analyze_sentence("ततः रामः गच्छति").edges
    r = analyze_sentence("ततः रामः गच्छति")
    named = {r.tokens[e.dependent].surface_slp1 for e in r.edges}
    assert "tatas" not in named
