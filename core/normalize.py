# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Stage 0 — transliteration / normalization to SLP1.

Accepts Devanagari OR Latin transliteration (IAST); everything downstream works in SLP1.
"""
from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_DEVANAGARI_RANGE = ("ऀ", "ॿ")


def _looks_devanagari(text: str) -> bool:
    return any(_DEVANAGARI_RANGE[0] <= c <= _DEVANAGARI_RANGE[1] for c in text)


#: The nukta (़ U+093C) marks Perso-Arabic sounds — क़ ख़ ग़ ज़ ड़ ढ़ फ़ — which classical Sanskrit
#: does not use. Transliteration leaves it in place, so a raw Devanagari codepoint survives into
#: what should be pure ASCII SLP1, and Vidyut's Rust splitter then PANICS on the byte boundary
#: rather than raising. Real Gītā text contains one, which is how this surfaced.
_NUKTA = "\u093c"

#: Sanskrit punctuation. The daṇḍa । closes a half-verse and the double daṇḍa ॥ closes a verse;
#: romanised text writes them | and ‖. They are punctuation, not letters — but nothing removed
#: them, so a verse written the normal way, with no space after the daṇḍa
#:
#:      ...bhuvanāni paryet ।pitā san...
#:
#: reached the tokenizer as the single token `.pitA`, which came out POS-unknown with no analysis
#: at all. Metre died with it: with the daṇḍa swallowed into a word, the reciter had no verse
#: boundary and measured the whole thing as one 65-mātrā pāda. No pāda is 65 mātrās.
#:
#: They become a SPACE rather than being deleted, because a daṇḍa IS a word boundary — deleting it
#: would fuse the words on either side into one. Devanagari digits are verse numbers (॥ २.४७ ॥)
#: and go the same way.
#:
#: The avagraha ऽ is deliberately NOT here: it is not punctuation, it marks an elided initial `a`
#: (Pāṇini 6.1.109 eṅaḥ padāntād ati), and dropping it would destroy a letter the sandhi needs.
#:
#: ASCII `.` is also deliberately absent — Velthuis uses it as a diacritic marker (`.t` = ṭ,
#: `.s` = ṣ), so stripping it would corrupt a scheme we accept. Removing the daṇḍa here, before
#: transliteration, means it never becomes a `.` in the first place.
_PUNCTUATION = str.maketrans({c: " " for c in "।॥|‖०१२३४५६७८९॰"})

#: A verse number is often written `॥ २.४७ ॥`, and once the digits are gone its separator `.` is
#: left stranded as a token of its own. Velthuis is the reason we cannot simply drop every `.`:
#: there it is a diacritic marker and ALWAYS immediately precedes a letter (`.t` = ṭ, `.s` = ṣ).
#: So a `.` NOT followed by a letter is punctuation and nothing else — which removes the stray
#: without touching `ko.spi` → kozpi.
_STRAY_DOT = re.compile(r"\.(?![A-Za-z])")

#: Vidyut's detected scheme name → the indic_transliteration constant. Built with getattr because
#: the two libraries do not name every script the same way (there is no `SINHALESE`), and a missing
#: one should simply be unsupported rather than an import-time crash.
_SCHEME_BY_NAME = {
    name: getattr(sanscript, attr)
    for name, attr in (
        ("devanagari", "DEVANAGARI"), ("iast", "IAST"), ("slp1", "SLP1"),
        ("harvardkyoto", "HK"), ("itrans", "ITRANS"), ("velthuis", "VELTHUIS"),
        ("wx", "WX"), ("iso15919", "IAST"), ("kannada", "KANNADA"), ("telugu", "TELUGU"),
        ("tamil", "TAMIL"), ("malayalam", "MALAYALAM"), ("bengali", "BENGALI"),
        ("gujarati", "GUJARATI"), ("gurmukhi", "GURMUKHI"), ("odia", "ORIYA"),
    )
    if hasattr(sanscript, attr)
}


def to_slp1(text: str) -> str:
    """Normalize Devanagari or IAST input to SLP1."""
    text = unicodedata.normalize("NFC", text).replace(_NUKTA, "")
    text = _STRAY_DOT.sub(" ", text.translate(_PUNCTUATION))
    if not text.strip():
        return ""
    text = _fix_adhoc_roman(text)
    return transliterate(text, _detect_scheme(text), sanscript.SLP1)


#: People write Sanskrit in many romanisations, and an engine that only accepts two will mangle the
#: rest silently. Before this, pasting SLP1 — our OWN internal form — turned `kzetra` into
#: `kj0etra`, because the input was assumed to be IAST. Detection is the fix; the table below is
#: only for styles no standard scheme covers.
#:
#: Popular romanisation inserts an `h` that no scheme uses: `kṣhetra`, `phaleṣhu`, `Kṛiṣhṇa`. The
#: Gītā source we ingest is written this way. It is applied ONLY when diacritics are present —
#: otherwise plain `kshetra` is valid ITRANS and rewriting it would break a scheme that works.
_ADHOC_ROMAN = (("kṣh", "kṣ"), ("ṣh", "ṣ"), ("śh", "ś"), ("ṇh", "ṇ"), ("ñh", "ñ"))

#: ISO 15919 differs from IAST in a handful of vowels and the anusvāra: it writes ē ō for e o
#: (Sanskrit has no short e/o, so the macron is redundant here), r̥ l̥ for ṛ ḷ, and ṁ for ṃ.
#: Folding them lets an ISO-encoded text be read as the IAST it is equivalent to.
_ISO_TO_IAST = (("ē", "e"), ("ō", "o"), ("Ē", "E"), ("Ō", "O"),
                ("r̥̄", "ṝ"), ("r̥", "ṛ"), ("l̥̄", "ḹ"), ("l̥", "ḷ"), ("ṁ", "ṃ"))

#: In plain ASCII with no diacritics, `ksh` is overwhelmingly kṣ rather than kś — "Krishna",
#: "kshetra", "moksha". ITRANS reads bare `sh` as ś, which is right for ITRANS and wrong for what
#: someone typing without diacritics actually means.
_ASCII_KSH = "ksh"
_DIACRITICS = "āīūṛṝḷḹṃḥśṣñṅṭḍṇēō"


def _fix_adhoc_roman(text: str) -> str:
    if not any(c in _DIACRITICS for c in text.lower()):
        # plain ASCII: only the ksh convention, then leave the rest to the detector
        return text.replace(_ASCII_KSH, "kṣ").replace("Ksh", "Kṣ").replace("KSH", "KṢ")
    out = text
    for wrong, right in _ISO_TO_IAST + _ADHOC_ROMAN:
        out = out.replace(wrong, right).replace(wrong.capitalize(), right.capitalize())
    return out


def _detect_scheme(text: str):
    """Which romanisation is this? Vidyut knows 50 of them; ask rather than assume.

    Devanagari is checked directly because detection on a mixed or very short string is less
    reliable than the codepoint range, and falls back to IAST — the commonest scholarly form —
    when detection cannot decide.
    """
    if _looks_devanagari(text):
        return sanscript.DEVANAGARI
    try:
        from vidyut.lipi import detect
        detected = detect(text)
    except Exception:                                # noqa: BLE001 — detection is best-effort
        return sanscript.IAST
    name = str(detected).lower()
    # SLP1, Harvard-Kyoto and WX share one ASCII alphabet and disagree about what its letters mean,
    # so on a short string detection genuinely cannot separate them: `Darma` is SLP1 *dharma* AND
    # Harvard-Kyoto *ḍarma*, with nothing in the text to decide. This is a property of the schemes,
    # not something a better heuristic fixes.
    #
    # What CAN be decided: SLP1 alone uses z (ṣ), f (ṛ), x (ḷ) and their capitals. When one of
    # those appears, the text is SLP1 and detection is overruled. When none does, we defer — and a
    # bare ASCII word like `Darma` may be read as another scheme. Callers holding SLP1 already
    # should not be round-tripping it through here.
    if _SLP1_MARKERS & set(text):
        return sanscript.SLP1
    return _SCHEME_BY_NAME.get(name, sanscript.IAST)


#: Characters only SLP1 uses in these senses — ṣ, ṛ, ḷ and their long forms. Harvard-Kyoto writes
#: those as S/z, R/RR, lR; WX differs again. Their presence settles the scheme; their absence does
#: not, which is why this is a marker set rather than an alphabet check.
_SLP1_MARKERS = frozenset("zfFxX")


def to_devanagari(slp1: str) -> str:
    return transliterate(slp1, sanscript.SLP1, sanscript.DEVANAGARI)


def to_iast(slp1: str) -> str:
    return transliterate(slp1, sanscript.SLP1, sanscript.IAST)


def to_pausa(word_slp1: str) -> str:
    """A pada's conventional WRITTEN form: final `s`/`r` become visarga.

    Two different forms of the same word are in play and conflating them is a real bug:

      * the **kosha-facing** form, which is what `_underlying()` produces and what lookup needs.
        Vidyut keys its lexicon on pre-visarga padas, so `budDiH` is rejected and `budDis` accepted.
      * the **written** form, which is how Sanskrit is actually set down and how DCS records it.
        In pausa a pada's final `s` or `r` is a visarga: भावः, not भावस्.

    We were displaying the kosha-facing form, so the reader (and the LLM grounding) saw असतस् and
    भावस् — forms no Sanskrit text writes. Keep `surface_slp1` for lookup; render through this.
    """
    if len(word_slp1) < 2:
        return word_slp1
    return word_slp1[:-1] + "H" if word_slp1[-1] in "sr" else word_slp1
