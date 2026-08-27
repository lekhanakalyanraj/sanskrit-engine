# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 2 — per-word morphological analysis, backed by Vidyut's kosha.

Vidyut resolves vocabulary sanskrit_parser could not (proper nouns, more verbs), labels gender
correctly, and exposes typed enums instead of SLP1 tag strings (see EVAL-vidyut.md).

Two Vidyut quirks handled here:
  • kosha keys are pre-visarga padas (`rAmas`, not `rAmaH`) — we feed it the segmenter's output;
  • a noun's default `.lemma` is the deep dhātu (kṛdanta analysis), so for the dictionary headword
    we prefer the **Basic** pratīpadika reading (`gaja`, not `gaj`).

Data lives in `vidyut-data/` (run `vidyut.download_data(...)` once); override with $VIDYUT_DATA.
"""
from __future__ import annotations

import os
from pathlib import Path

from vidyut.prakriya import Lakara, Linga, Purusha, Vacana, Vibhakti

from .models import Analysis

# Vidyut enums → our canonical feature strings.
VIBHAKTI = {
    Vibhakti.Prathama: "nominative", Vibhakti.Dvitiya: "accusative",
    Vibhakti.Trtiya: "instrumental", Vibhakti.Caturthi: "dative",
    Vibhakti.Panchami: "ablative", Vibhakti.Sasthi: "genitive",
    Vibhakti.Saptami: "locative", Vibhakti.Sambodhana: "vocative",
}
LINGA = {Linga.Pum: "masculine", Linga.Stri: "feminine", Linga.Napumsaka: "neuter"}
VACANA = {Vacana.Eka: "singular", Vacana.Dvi: "dual", Vacana.Bahu: "plural"}
PURUSHA = {Purusha.Prathama: "third", Purusha.Madhyama: "second", Purusha.Uttama: "first"}
LAKARA = {
    Lakara.Lat: "present (laṭ)", Lakara.Lit: "perfect (liṭ)", Lakara.Lut: "periph. future (luṭ)",
    Lakara.Lrt: "future (lṛṭ)", Lakara.Lot: "imperative (loṭ)", Lakara.Lan: "imperfect (laṅ)",
    Lakara.VidhiLin: "optative (vidhi-liṅ)", Lakara.AshirLin: "benedictive (āśīr-liṅ)",
    Lakara.Lun: "aorist (luṅ)", Lakara.Lrn: "conditional (lṛṅ)", Lakara.Let: "subjunctive (leṭ)",
}

DATA_DIR = Path(os.environ.get("VIDYUT_DATA", Path(__file__).resolve().parent.parent / "vidyut-data"))
_KOSHA = None


def kosha():
    """Lazy singleton for the Vidyut kosha."""
    global _KOSHA
    if _KOSHA is None:
        from vidyut.kosha import Kosha
        _KOSHA = Kosha(str(DATA_DIR / "kosha"))
    return _KOSHA


def is_valid_word(word_slp1: str) -> bool:
    """Does the kosha recognize this surface form? Used by segmentation."""
    return bool(kosha().get(word_slp1))


def _map_entry(entry) -> tuple[Analysis, bool]:
    """Map a Vidyut PadaEntry → (Analysis, is_basic_noun). Verbs count as 'basic'."""
    lakara = getattr(entry, "lakara", None)
    if lakara is not None:  # Tinanta (finite verb)
        features = {"tense": LAKARA.get(lakara, str(lakara))}
        if (pur := getattr(entry, "purusha", None)) is not None:
            features["person"] = PURUSHA.get(pur, str(pur))
        if (vac := getattr(entry, "vacana", None)) is not None:
            features["number"] = VACANA.get(vac, str(vac))
        return Analysis(lemma=entry.lemma, pos="verb", features=features, raw_tags=["verb"]), True

    # Subanta (nominal)
    pe = getattr(entry, "pratipadika_entry", None)
    is_basic = pe is not None and getattr(pe, "dhatu_entry", None) is None
    lemma = (getattr(pe, "lemma", None) if is_basic else None) or entry.lemma

    features: dict[str, str] = {}
    vibhakti = getattr(entry, "vibhakti", None)
    if vibhakti is not None:
        features["case"] = VIBHAKTI.get(vibhakti, str(vibhakti))
    if (linga := getattr(entry, "linga", None)) is not None:
        features["gender"] = LINGA.get(linga, str(linga))
    if (vac := getattr(entry, "vacana", None)) is not None:
        features["number"] = VACANA.get(vac, str(vac))
    pos = "noun" if vibhakti is not None else "other"
    return Analysis(lemma=lemma, pos=pos, features=features, raw_tags=[]), is_basic


def analyze_candidates(word_slp1: str) -> list[Analysis]:
    """All morphological readings of a word, deduped and in a DETERMINISTIC order.

    Prefers Basic (non-kṛdanta) noun readings so headwords stay clean, then dedupes Vidyut's many
    paradigm-slot repeats. Picking one reading per token is disambiguation's job.
    """
    entries = kosha().get(word_slp1) or []
    if not entries:
        return [Analysis(lemma=word_slp1, pos="unknown", features={}, raw_tags=[])]

    mapped = [_map_entry(e) for e in entries]
    has_basic_noun = any(is_basic and a.pos == "noun" for a, is_basic in mapped)

    seen: set[tuple] = set()
    cands: list[Analysis] = []
    for a, is_basic in mapped:
        # drop deep-root (kṛdanta) noun readings when a clean Basic reading exists for this word
        if a.pos == "noun" and not is_basic and has_basic_noun:
            continue
        key = (a.pos, a.lemma, a.features.get("case", ""), a.features.get("number", ""),
               a.features.get("gender", ""), a.features.get("tense", ""), a.features.get("person", ""))
        if key in seen:
            continue
        seen.add(key)
        cands.append(a)

    cands.sort(key=lambda a: (a.pos, a.features.get("case", ""), a.lemma,
                              a.features.get("number", ""), a.features.get("gender", "")))
    return cands
