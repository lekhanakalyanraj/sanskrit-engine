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
from core.normalize import to_pausa
from core.pronounce import pronounce
from core.recite import scan
from agents.explainer import senses_for
from knowledge.dictionary import attach_senses
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

@st.cache_data(show_spinner="Reading the page…")
def _ocr(image_bytes: bytes) -> str:
    """OCR is slow (a VLM through llama.cpp), so cache on the image itself."""
    import tempfile
    from core.ocr import OllamaVision
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(image_bytes)
        path = fh.name
    return OllamaVision().read(path)


with st.expander("Read from an image", expanded=False):
    st.caption("Photograph or scan a printed page. OCR output is checked word-by-word against the "
               "lexicon before you parse it — Devanagari OCR drops vowel marks and confuses "
               "व/ब, घ/ध, भ/म, so the misreads are predictable and worth catching. "
               "Handwritten and palm-leaf manuscripts will not work: no off-the-shelf OCR reads them.")
    _upload = st.file_uploader("Page image", type=["png", "jpg", "jpeg", "webp", "tif", "tiff"])
    if _upload is not None:
        st.image(_upload, use_container_width=True)
        try:
            _text = _ocr(_upload.getvalue())
        except Exception as _e:  # noqa: BLE001 — surface backend/setup failures plainly
            _text = ""
            st.error(f"OCR failed: {_e}")
        if not _text.strip():
            st.error("OCR returned no text. That is a failure, not a clean page — check the image "
                     "is legible and right-way-up, or try a higher-resolution capture.")
        if _text.strip():
            from core.ocr import validate as _validate
            from core.normalize import to_devanagari as _dev
            _suspects = _validate(_text)
            if _suspects:
                st.warning(f"{len(_suspects)} word(s) the lexicon does not recognise — "
                           f"correct them below before parsing.")
                for _s in _suspects[:8]:
                    _alt = "  ·  ".join(_dev(g) for g in _s.suggestions) or "no suggestion"
                    st.caption(f"**{_s.devanagari}** → {_alt}   _{_s.reason}_")
            else:
                st.success("Every word checks out against the lexicon.")
            st.session_state["ocr_text"] = _text

col_in, col_provider = st.columns([3, 1])
with col_in:
    sentence = st.text_input("Sanskrit sentence (Devanagari or IAST)",
                             st.session_state.get("ocr_text", GOLD_EXAMPLES[0]))
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

# ── Recitation ────────────────────────────────────────────────────────────
st.subheader("Recitation")

_sc = scan(sentence)
if not _sc.aksharas:
    st.caption("Could not scan this input for metre.")
else:
    _head = _sc.metre or "metre not identified"
    if _sc.form:
        _head += f" · {_sc.form}"
    st.markdown(f"**{_head}** · {_sc.matras()} mātrās")
    st.caption("A long syllable is held twice as long as a short one — that is the whole of the "
               "timing. Pause at ‖, breathe at ‖‖. The tune is learned by ear from a reciter; "
               "what a text can give you is which syllables to hold and where to stop.")

    for _r in _sc.read_along():
        _syl = "  ".join(f"{s:<7s}" for s in _r["syllables"]) + _r["pause"]
        _hold = "  ".join(f"{h:<7s}" for h in _r["hold"])
        st.markdown(f"**pāda {_r['pada']}** · {_r['matras']} mātrās")
        st.code(f"{_syl}\n{_hold}", language=None)

    if len(_sc.padas) > 1:
        _a, _b = _sc.read_along()[0]["matras"], _sc.read_along()[1]["matras"]
        if _a != _b:
            st.caption(f"The first pāda runs {_a} beats and the second {_b} — that drop is the "
                       f"shape of the śloka, and you should be able to hear it.")

    for _n in _sc.notes:
        st.caption(f"• {_n}")

    with st.expander("Metrical pattern (⏑ / —)", expanded=False):
        st.code("   |   ".join("".join("—" if w == "G" else "⏑" for w in pada)
                               for pada in _sc.padas), language=None)
        st.caption("— guru (heavy) · ⏑ laghu (light). Heavy if the vowel is long, or a short "
                   "vowel is closed by a consonant cluster, anusvāra or visarga.")

with st.expander("Approximate English pronunciation", expanded=False):
    _said = [pronounce(to_pausa(t.surface_slp1)) for t in result.tokens]
    st.markdown("### " + "  ·  ".join(p.respelling for p in _said if p.respelling))
    for _n in list(dict.fromkeys(n for p in _said for n in p.notes)):
        st.caption(f"• {_n}")
    st.caption("Approximate, and secondary to the scansion above. Short `a` is the vowel of *but*, "
               "not *father* — `dharma` is DHUR-muh. CAPITALS follow the Latin-derived convention "
               "Western pedagogy teaches; classical Sanskrit has no phonemic stress, so this is a "
               "reading aid, not a fact about the language.")

# ── Meaning (Phase 2: word-level dictionary senses) ───────────────────────
st.subheader("Meaning")
st.caption("Word-by-word dictionary senses. Sanskrit words are layered — expand a word to see its "
           "full range, which is where the meaning actually lives.")
cols = st.columns(len(result.tokens) or 1)
for col, t in zip(cols, result.tokens):
    role = next((e.role for e in result.edges if e.dependent == t.id), "verb" if t.analysis.pos == "verb" else "")
    with col:
        st.markdown(f"**{t.surface}**")
        st.caption(f"{pronounce(to_pausa(t.surface_slp1)).respelling}")
        st.caption(f"{to_iast(t.analysis.lemma)}  ·  {role}" if role else to_iast(t.analysis.lemma))
        if t.senses:
            st.write(t.senses[0].gloss)
            extra = senses_for(t)[1:]
            if extra:
                with st.expander(f"{len(extra)} more senses"):
                    for g in extra:
                        st.caption(f"• {g}")
        else:
            st.write("—")

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
            expl = explain(result)
            verdict = verify(expl, build_grounding(result), result)
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
