# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Streamlit dev playground — the primary way to poke at the engine.

    streamlit run playground.py

Shows every stage of the deterministic core for any sentence, plus the kāraka graph.
Retrieval (Phase 2) and grounded explanation via the selected provider (Phase 3) are stubbed.
"""
from __future__ import annotations

import streamlit as st
from streamlit.components.v1 import html as st_html

from core import analyze_sentence, to_iast
from knowledge.dictionary import attach_senses
from knowledge.vectorstore import related_passages
from llm import PRESETS
from render import render

st.set_page_config(page_title="Sanskrit Engine — Playground", layout="wide")
st.title("Sanskrit Understanding Engine — dev playground")
st.caption("Deterministic core: normalize → segment → morphology → kāraka graph. No LLM, no training.")

GOLD_EXAMPLES = [
    "बालः हस्तेन अन्नं खादति",
    "बालः फलं खादति",
    "नरः जलं पिबति",
    "गजः वनं गच्छति",
]

col_in, col_provider = st.columns([3, 1])
with col_in:
    sentence = st.text_input("Sanskrit sentence (Devanagari or IAST)", GOLD_EXAMPLES[0])
    st.caption("Try: " + " · ".join(GOLD_EXAMPLES[1:]))
with col_provider:
    provider = st.selectbox("LLM provider (Phase 3)", list(PRESETS.keys()))

if not sentence.strip():
    st.stop()

try:
    result = analyze_sentence(sentence)
    attach_senses(result)  # Stage 3 — fill each token's dictionary meaning
except Exception as e:  # noqa: BLE001 — surface parse failures to the user
    st.error(f"Could not parse this sentence: {e}")
    st.info("Sandhi/vocabulary gaps still happen on hard input. Try one of the examples above.")
    st.stop()

# ── Hero: the kāraka graph ────────────────────────────────────────────────
st.subheader("Kāraka dependency graph")
st_html(render(result.to_graph_dict()), height=620, scrolling=False)

# ── Per-stage inspector ───────────────────────────────────────────────────
left, right = st.columns(2)
with left:
    with st.expander("Stage 0 · Normalize", expanded=False):
        st.json({"input": sentence, "SLP1": result.sentence_slp1, "IAST": to_iast(result.sentence_slp1)})
    with st.expander("Stage 1 · Segmentation (sandhi split)", expanded=True):
        st.write([t.surface_slp1 for t in result.tokens])
with right:
    with st.expander("Stage 2 · Morphology + meaning", expanded=True):
        st.table([
            {"surface": t.surface, "lemma": t.analysis.lemma, "pos": t.analysis.pos,
             "case/tense": t.analysis.features.get("case") or t.analysis.features.get("tense", ""),
             "meaning": ((t.senses[0].gloss[:70] + "…") if len(t.senses[0].gloss) > 70 else t.senses[0].gloss)
                        if t.senses else "—"}
            for t in result.tokens if t.analysis
        ])
    with st.expander("Stage 4 · Kāraka edges", expanded=True):
        st.table([
            {"dependent": result.tokens[e.dependent].surface, "role": e.role,
             "head": result.tokens[e.head].surface}
            for e in result.edges
        ] or [{"note": "no edges (no finite verb found)"}])

# ── Meaning (Phase 2: word-level dictionary senses) ───────────────────────
st.subheader("Meaning")
st.caption("Word-by-word dictionary senses (symbolic lookup). Read with the kāraka graph above: "
           "who does what to whom, and what each word means.")
cols = st.columns(len(result.tokens) or 1)
for col, t in zip(cols, result.tokens):
    role = next((e.role for e in result.edges if e.dependent == t.id), "verb" if t.analysis.pos == "verb" else "")
    with col:
        st.markdown(f"**{t.surface}**")
        st.caption(f"{to_iast(t.analysis.lemma)}  ·  {role}" if role else to_iast(t.analysis.lemma))
        st.write(t.senses[0].gloss if t.senses else "—")

# ── Essence: related passages (vector retrieval) ──────────────────────────
st.subheader("Related passages · essence")
st.caption("Verses whose meaning is closest to this sentence — semantic retrieval (Qdrant + BGE) "
           "over a seed corpus. The 'meaning is retrieved' half of the engine.")
hits: list = []
try:
    with st.spinner("retrieving related verses…"):
        hits = related_passages(result, k=3)
    if hits:
        for h in hits:
            st.markdown(f"**{h['sanskrit_dev']}**  ·  *{h.get('iast', '')}*")
            st.caption(f"{h['translation']}  —  {h['source']}  ·  score {h['score']}")
    else:
        st.write("— no related passages")
except Exception as e:  # noqa: BLE001 — vector store is optional; don't break the page
    st.warning(f"Vector store unavailable: {e}")

# ── Grounded reading + verifier (Phase 3, LLM) ────────────────────────────
import os

st.subheader("Grounded reading")
st.caption("An LLM phrases the structure + meanings + passages into a faithful reading — no grammar, "
           "no invented facts. The verifier checks it and reports a confidence signal.")

model_name = os.environ.get("LLM_MODEL", "qwen2.5:7b" if provider == "ollama" else "provider default")
if st.button(f"Generate reading  ·  {provider} · {model_name}"):
    import llm as _llm
    os.environ["LLM_PROVIDER"] = provider
    _llm.reset()  # pick up the chosen provider
    try:
        from agents.explainer import build_grounding, explain
        from agents.verifier import verify
        with st.spinner(f"asking {provider} ({model_name})… first call also loads the model"):
            expl = explain(result, hits)
            verdict = verify(expl, build_grounding(result, hits), result)
        st.session_state["reading"] = {"sentence": sentence, "provider": provider,
                                       "expl": expl, "verdict": verdict}
    except Exception as e:  # noqa: BLE001 — no LLM reachable is a normal dev state
        st.session_state["reading"] = {"sentence": sentence, "provider": provider, "error": str(e)}

rd = st.session_state.get("reading")
if rd and rd.get("sentence") == sentence:              # persist across reruns for this sentence
    if "error" in rd:
        st.error(f"LLM provider **{rd['provider']}** unreachable: {rd['error']}")
        st.caption("Ollama runs as a background service — no `ollama serve` needed. "
                   "Pull the model with `ollama pull qwen2.5:7b`, or set an API key and pick another provider.")
    else:
        expl, verdict = rd["expl"], rd["verdict"]
        st.markdown(f"**Translation** — {expl.translation}")
        st.markdown(f"**Reading** — {expl.reading}")
        badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(verdict.confidence, "⚪")
        st.markdown(f"**Confidence** — {badge} {verdict.confidence}  ·  grounded: {verdict.grounded}  ·  via {rd['provider']}")
        if verdict.issues:
            st.warning("Verifier flags — " + "; ".join(verdict.issues))
