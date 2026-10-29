# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Dictionary curation tool — browse the data, mark what's unclean, fix and add meanings.

    streamlit run curate.py

The MW cleaner is heuristic. This is the human layer on top: look at the actual data, flag junk,
correct glosses, add senses the dictionary is missing. Everything is written to
`knowledge/curation.yaml`, which survives re-ingestion and is meant to be committed.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from core.normalize import to_iast
from knowledge.curation import (ADD, EDIT, FLAG, HIDE, add_rule, mark_reviewed, remove_rule,
                                reviewed_set, rules_for, stats, suspicion_flags)
from knowledge.dictionary import _DB, build_db, lookup

st.set_page_config(page_title="Dictionary curation", layout="wide")


@st.cache_resource
def conn():
    if not _DB.exists():
        build_db()
    return sqlite3.connect(str(_DB), check_same_thread=False)


@st.cache_data(ttl=30)
def overview() -> dict:
    c = conn()
    total = c.execute("SELECT COUNT(*) FROM sense").fetchone()[0]
    lemmas = c.execute("SELECT COUNT(DISTINCT lemma) FROM sense").fetchone()[0]
    by_source = dict(c.execute("SELECT source, COUNT(*) FROM sense GROUP BY source").fetchall())
    per_lemma = c.execute(
        "SELECT n, COUNT(*) FROM (SELECT lemma, COUNT(*) n FROM sense GROUP BY lemma) GROUP BY n "
        "ORDER BY n LIMIT 25").fetchall()
    return {"total": total, "lemmas": lemmas, "by_source": by_source, "per_lemma": per_lemma}


# SLP1 uses capitals and odd letters for sounds English lacks (f = ṛ, z = ṣ, R = ṇ, K = kh …).
# Most people will type "krsna" or "dharma" with no diacritics at all, so we also match on a bare
# ASCII "skeleton" of every lemma.
_SKELETON = {
    "A": "a", "I": "i", "U": "u", "f": "r", "F": "r", "x": "l", "X": "l", "E": "e", "O": "o",
    "K": "kh", "G": "gh", "N": "n", "C": "ch", "J": "jh", "Y": "n", "w": "t", "W": "th",
    "q": "d", "Q": "dh", "R": "n", "T": "th", "D": "dh", "P": "ph", "B": "bh",
    "S": "s", "z": "s", "M": "m", "H": "h", "'": "",
}


def skeleton(word: str) -> str:
    return "".join(_SKELETON.get(ch, ch) for ch in word).lower()


@st.cache_data(ttl=300)
def skeleton_index() -> dict[str, list[str]]:
    """bare-ASCII form → lemmas, so diacritic-free typing still finds the word."""
    index: dict[str, list[str]] = {}
    for (lemma,) in conn().execute("SELECT DISTINCT lemma FROM sense"):
        index.setdefault(skeleton(lemma), []).append(lemma)
    return index


@st.cache_data(ttl=60)
def find_lemmas(query: str, limit: int = 40) -> list[tuple[str, int]]:
    """Match a word typed in Devanagari, IAST or SLP1 — nobody should have to know SLP1."""
    forms = {query.strip()}
    try:
        forms.add(to_slp1(query.strip()))       # devanagari/IAST → SLP1
    except Exception:                            # noqa: BLE001
        pass
    seen, out = set(), []
    for form in filter(None, forms):
        rows = conn().execute(
            "SELECT lemma, COUNT(*) n FROM sense WHERE lemma LIKE ? GROUP BY lemma "
            "ORDER BY (lemma = ?) DESC, n DESC LIMIT ?", (f"{form}%", form, limit)).fetchall()
        for lemma, n in rows:
            if lemma not in seen:
                seen.add(lemma)
                out.append((lemma, n))

    if len(out) < limit:                      # diacritic-free fallback: "krsna" → kfzRa
        want = skeleton(query.strip())
        for skel, lemmas in skeleton_index().items():
            if skel.startswith(want):
                for lemma in lemmas:
                    if lemma not in seen:
                        seen.add(lemma)
                        n = conn().execute("SELECT COUNT(*) FROM sense WHERE lemma=?",
                                           (lemma,)).fetchone()[0]
                        out.append((lemma, n))
            if len(out) >= limit:
                break
    return sorted(out, key=lambda p: -p[1])[:limit]


@st.cache_data(ttl=60)
def build_queue(kind: str, size: int = 500) -> list[str]:
    """An ordered worklist, so review can proceed one word at a time."""
    c = conn()
    if kind == "Most senses first":
        rows = c.execute("SELECT lemma FROM sense GROUP BY lemma ORDER BY COUNT(*) DESC LIMIT ?",
                         (size,)).fetchall()
    elif kind == "Words the engine uses (gold set)":
        import yaml
        from pathlib import Path
        lemmas: list[str] = []
        for f in sorted((Path(__file__).parent / "gold").glob("*.yaml")):
            for entry in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
                lemmas += [t["lemma"] for t in entry.get("tokens", []) if t.get("lemma")]
        seed = yaml.safe_load((Path(__file__).parent / "knowledge" / "dictionary.yaml")
                              .read_text(encoding="utf-8")) or {}
        ordered = list(dict.fromkeys(lemmas + list(seed)))
        return ordered[:size]
    elif kind == "Suspect glosses":
        rows = c.execute("SELECT lemma, gloss, source FROM sense ORDER BY RANDOM() LIMIT ?",
                         (size * 12,)).fetchall()
        hits = list(dict.fromkeys(l for l, g, src in rows if suspicion_flags(g, src)))
        return hits[:size]
    else:                                        # Alphabetical
        rows = c.execute("SELECT DISTINCT lemma FROM sense ORDER BY lemma LIMIT ?", (size,)).fetchall()
    return [r[0] for r in rows]


st.title("Dictionary curation")
o = overview()
c1, c2, c3, c4 = st.columns(4)
c1.metric("senses", f"{o['total']:,}")
c2.metric("lemmas", f"{o['lemmas']:,}")
c3.metric("sources", ", ".join(f"{k}:{v:,}" for k, v in o["by_source"].items()))
c4.metric("curation rules", stats()["rules"])

browse, review, explore = st.tabs(["🔎 Browse & curate", "🚩 Needs review", "📊 Understand the data"])

# ── Browse a lemma and curate its senses ─────────────────────────────────────
with browse:
    mode = st.radio("find a word by", ["Search", "Review queue"], horizontal=True,
                    label_visibility="collapsed")
    lemma = ""

    if mode == "Search":
        typed = st.text_input("Word — type Devanagari, IAST or SLP1",
                              placeholder="धर्म  ·  dharma  ·  Darma")
        if typed.strip():
            matches = find_lemmas(typed)
            if matches:
                choice = st.selectbox(
                    f"{len(matches)} match(es)", matches,
                    format_func=lambda m: f"{m[0]}  ({to_iast(m[0])})  —  {m[1]} sense(s)")
                lemma = choice[0]
            else:
                st.warning("No lemma starts with that. Try the IAST spelling, e.g. `bhāva` or `dharma`.")

    else:
        qcols = st.columns([3, 1])
        kind = qcols[0].selectbox("queue", ["Words the engine uses (gold set)", "Most senses first",
                                            "Suspect glosses", "Alphabetical"])
        skip_done = qcols[1].checkbox("hide reviewed", value=True)

        queue = build_queue(kind)
        done = reviewed_set()
        if skip_done:
            queue = [w for w in queue if w not in done] or queue

        if not queue:
            st.info("Queue is empty.")
        else:
            key = f"idx::{kind}::{skip_done}"
            idx = min(st.session_state.get(key, 0), len(queue) - 1)
            nav = st.columns([1, 1, 3, 2])
            if nav[0].button("← prev", disabled=idx == 0):
                st.session_state[key] = idx - 1
                st.rerun()
            if nav[1].button("next →", disabled=idx >= len(queue) - 1):
                st.session_state[key] = idx + 1
                st.rerun()
            lemma = queue[idx]
            nav[2].progress((idx + 1) / len(queue),
                            text=f"{idx + 1} / {len(queue)}   ·   {len(done)} reviewed overall")
            if nav[3].button("✓ mark reviewed & next", type="primary"):
                mark_reviewed(lemma)
                st.session_state[key] = min(idx + 1, len(queue) - 1)
                st.rerun()
            if lemma in done:
                st.caption("✓ already reviewed")

    if lemma:
        senses = lookup(lemma)                     # curation already applied
        st.caption(f"**{lemma}** ({to_iast(lemma)}) — {len(senses)} sense(s) after curation")

        existing = rules_for(lemma)
        if existing:
            with st.expander(f"{len(existing)} curation rule(s) on this lemma", expanded=False):
                for ri, r in enumerate(existing):
                    cols = st.columns([1, 4, 1])
                    cols[0].code(r["action"])
                    cols[1].caption(f"{r.get('gloss', '')[:70]} → {r.get('replacement', '')[:70]}"
                                    f"{'  · ' + r['note'] if r.get('note') else ''}")
                    # key must be unique: two rules can share a gloss prefix, so index it
                    if cols[2].button("undo", key=f"undo-{lemma}-{ri}"):
                        remove_rule(lemma, r["action"], r.get("gloss", ""))
                        st.rerun()

        st.divider()
        for i, s in enumerate(senses):
            flags = suspicion_flags(s.gloss, s.source)
            left, right = st.columns([5, 2])
            with left:
                st.markdown(f"**{i + 1}.** {s.gloss}")
                st.caption(f"source: `{s.source}`" + (f"  ·  ⚠ {', '.join(flags)}" if flags else ""))
            with right:
                b1, b2 = st.columns(2)
                if b1.button("🚩 flag", key=f"flag-{lemma}-{i}", help="mark as unclean, keep it visible"):
                    add_rule(lemma, FLAG, gloss=s.gloss, note=", ".join(flags))
                    st.rerun()
                if b2.button("🗑 hide", key=f"hide-{lemma}-{i}", help="remove from what the engine sees"):
                    add_rule(lemma, HIDE, gloss=s.gloss, note=", ".join(flags))
                    st.rerun()
                with st.popover("✏️ edit"):
                    new = st.text_area("corrected gloss", s.gloss, key=f"edit-{lemma}-{i}", height=100)
                    if st.button("save", key=f"save-{lemma}-{i}") and new.strip() != s.gloss:
                        add_rule(lemma, EDIT, gloss=s.gloss, replacement=new.strip())
                        st.rerun()

        st.divider()
        with st.form(f"add-{lemma}", clear_on_submit=True):
            st.markdown("**Add a meaning** — curated senses are shown first, ahead of MW's.")
            new_gloss = st.text_input("gloss", placeholder="e.g. becoming, being, existing")
            note = st.text_input("note (optional)", placeholder="why you added it")
            if st.form_submit_button("add") and new_gloss.strip():
                add_rule(lemma, ADD, replacement=new_gloss.strip(), note=note.strip())
                st.rerun()

# ── Queue of likely-unclean data ─────────────────────────────────────────────
with review:
    st.caption("Glosses matching cleanliness heuristics — a queue to work through, not a verdict.")
    colf, coln = st.columns([3, 1])
    chosen = colf.multiselect(
        "show glosses flagged as", ["very short", "markup residue", "proper name",
                                    "starts mid-parenthesis", "scholarly shorthand",
                                    "cross-reference", "grammatical apparatus", "citation digits"],
        default=["markup residue", "scholarly shorthand", "grammatical apparatus"])
    limit = coln.number_input("sample size", 200, 20000, 2000, step=200)

    if st.button("scan"):
        rows = conn().execute(
            "SELECT lemma, source, gloss FROM sense ORDER BY RANDOM() LIMIT ?", (int(limit),)).fetchall()
        hits = []
        for lem, src, gl in rows:
            fl = suspicion_flags(gl, src)
            if chosen and set(fl) & set(chosen):
                hits.append({"lemma": lem, "iast": to_iast(lem), "flags": ", ".join(fl),
                             "gloss": gl[:130], "source": src})
        st.metric("suspect glosses in sample", f"{len(hits):,}",
                  f"{100 * len(hits) / max(len(rows), 1):.1f}% of {len(rows):,} sampled")
        if hits:
            st.dataframe(pd.DataFrame(hits), use_container_width=True, height=460)
            st.caption("Copy a lemma into **Browse & curate** to fix it.")

# ── Shape of the dataset ─────────────────────────────────────────────────────
with explore:
    st.subheader("How many senses does a word have?")
    df = pd.DataFrame(o["per_lemma"], columns=["senses per lemma", "number of lemmas"])
    st.bar_chart(df.set_index("senses per lemma"))
    st.caption("The long tail is the point: `dharma`, `yoga` and `rasa` carry dozens of senses. "
               "Feeding the engine only the first one is what made translations flat.")

    st.subheader("Words with the most senses")
    top = conn().execute(
        "SELECT lemma, COUNT(*) n FROM sense GROUP BY lemma ORDER BY n DESC LIMIT 30").fetchall()
    st.dataframe(pd.DataFrame([{"lemma": l, "iast": to_iast(l), "senses": n} for l, n in top]),
                 use_container_width=True, height=320)

    st.subheader("Curation so far")
    st.json(stats())
