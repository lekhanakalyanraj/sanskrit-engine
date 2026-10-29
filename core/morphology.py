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

# Indeclinables (avyaya). A CLOSED class, so this is a fact about Sanskrit rather than a
# heuristic. The kosha happily analyses `na` ("not") as the noun `nā` ("the navel"), which then
# becomes a kāraka argument and derails the whole parse — particles must never be inflected and
# never take a role.
PARTICLES: dict[str, str] = {
    "na": "not, no", "ca": "and", "eva": "indeed, only, verily", "vA": "or",
    "hi": "for, indeed", "tu": "but", "vE": "indeed", "iti": "thus, so (end of quote)",
    "api": "also, even", "mA": "do not (prohibitive)", "sma": "(past marker)",
    "Kalu": "indeed", "punar": "again", "atha": "now, then", "aTa": "now, then",
    "uta": "and, also", "cet": "if", "yadi": "if", "taTA": "thus, so", "yaTA": "as, just as",
    "iva": "like, as if", "saha": "with", "vinA": "without", "nUnam": "surely",
    # ── nipāta / svarādi avyaya (1.1.37 svarādinipātam avyayam) ─────────────────────────────────
    # A closed list in the grammar, so transcribing it is a fact about Sanskrit, not tuning. These
    # are the ones the lexicon's own avyaya flag misses because MW also carries a spurious nominal
    # entry for them — `evam` was being inflected and handed a kāraka role 43 times in our sample.
    "evam": "thus, in this way", "iha": "here, in this world", "ha": "indeed (emphatic)",
    "aTo": "and then", "nanu": "surely, is it not", "kila": "indeed, they say",
    "nUnam": "certainly", "nAma": "by name, indeed", "nAnA": "variously, diverse",
    "adya": "today", "sadA": "always", "sarvadA": "always", "kadA": "when",
    "adhunA": "now", "idAnIm": "now", "muhur": "repeatedly", "BUyas": "again, further",
    "alam": "enough, sufficient", "vinA": "without", "fte": "except, without",
    "saha": "together with", "antarA": "between", "antareRa": "without",
    "paScAt": "afterwards, behind", "pUrvam": "formerly, before", "prAk": "before, eastward",
    "uccEs": "loudly, high", "nIcEs": "softly, low", "SanEs": "slowly",
    "bahis": "outside", "antar": "within", "upari": "above", "aDas": "below",
    "sAkzAt": "directly, visibly", "mizyA": "falsely", "mudDA": "in vain",
    "kvacid": "somewhere, sometimes", "kutas": "whence, why", "kva": "where",
    # -cana / -cid / -api indefinites are single indeclinables. `kadAcana` was being split into
    # `kat` + `Acana` and glossed "to accumulate", which is how a real reader found this.
    "kadAcana": "ever, at any time", "kadAcit": "sometimes, once",
    "kaScana": "someone, any", "kiYcana": "anything, somewhat", "kiYcit": "something, a little",
    # `kiYcit` and `kiMcid` are one word: the nasal is written by anusvāra or by the
    # class nasal, and the final stop voices before a vowel. Both spellings occur in
    # print, and only one was listed, so the other fell through as POS-unknown.
    "kiMcit": "something, a little", "kiMcid": "something, a little",
    "kiYcid": "something, a little", "kaScit": "someone, some", "kaScid": "someone, some",
    "sarvatra": "everywhere", "anyatra": "elsewhere", "ekadA": "once, at one time",
}

#: UPASARGA — the prādi list, the 22 items Pāṇini names at 1.4.58-59. A CLOSED class, so writing
#: it down is transcription, exactly like the nipāta and sarvanāma lists.
#:
#: Why these must never be nominals. 1.4.59 `upasargāḥ kriyāyoge` calls them upasarga when joined
#: to a verbal action; 1.4.83 ff. call them karmapravacanīya elsewhere; 1.1.37 covers the rest as
#: nipāta. Those are the only three things they can be — and NONE of them is an inflected noun. So
#: the safe rule is not "attach them to a verb" but the weaker, airtight one: they never decline
#: and never fill a kāraka slot.
#:
#: That distinction matters, because the obvious rule — "upasarga when a verb follows" — is wrong.
#: `api` overwhelmingly means "also", and a verb almost always follows it somewhere; that rule
#: would have relabelled every one of them. Dropping the verb condition avoids the trap entirely.
#:
#: Checked before assuming: across the 6 DCS texts these forms occur 72 times as standalone
#: tokens and DCS tags them ADP, PART or ADV — **zero** NOUN or ADJ, 0.0%. The grammar says they
#: cannot be nominals and the corpus agrees, so this is not a judgement call.
#:
#: Left unhandled, the kosha declines them: `upa` returned exactly one reading, "nominative
#: masculine", and `saṃ` in `saṃ bhuvanāny ābharat` came back a noun glossed "to be calm" —
#: then entered the kāraka graph as an argument of a verb it is actually a prefix of.
UPASARGAS: dict[str, str] = {
    "pra": "forth, forward, onward", "parA": "away, back, aside",
    "apa": "away, off, down", "sam": "together, completely, fully",
    "anu": "after, along, following", "ava": "down, away, off",
    "nis": "out, away, without", "nir": "out, away, without",
    "dus": "ill, badly, hard", "dur": "ill, badly, hard",
    "vi": "apart, asunder, particularly", "A": "towards, near, back",
    "ni": "down, into, within", "aDi": "over, upon, above",
    "ati": "beyond, over, past", "su": "well, easily, very",
    "ud": "up, upwards, out", "aBi": "towards, against, unto",
    "prati": "back, towards, against, each", "pari": "around, about, fully",
    "upa": "near, towards, under",
    # `api` is deliberately absent: it is already in PARTICLES with its commonest sense
    # ("also, even"), which DCS confirms 46/46. Adding it here would only overwrite a better gloss.
}


#: ENAD — the anaphoric pronoun, a CLOSED paradigm the kosha does not carry at all, so every one
#: of its forms arrived POS-unknown and took no case.
#:
#: Pāṇini 2.4.34 `dvitīyāṭaussveneḥ` substitutes `enad` for `etad`/`idam` in exactly three
#: environments — dvitīyā (accusative), ṭā (instrumental singular) and os (genitive/locative dual).
#: That restriction is why the paradigm below is small and has gaps: there is no nominative enad,
#: because 2.4.34 does not license one. Writing a closed paradigm down is transcription, the same
#: as the nipāta list (1.1.37) and the sarvanāma list (1.1.27).
#:
#: Measured: 15 tokens across five corpora, every one previously caseless.
ENAD: dict[str, dict[str, str]] = {
    # dvitīyā (2.4.34)
    "enam":   {"case": "accusative",   "gender": "masculine", "number": "singular"},
    "enat":   {"case": "accusative",   "gender": "neuter",    "number": "singular"},
    "enad":   {"case": "accusative",   "gender": "neuter",    "number": "singular"},
    "enAm":   {"case": "accusative",   "gender": "feminine",  "number": "singular"},
    "enO":    {"case": "accusative",   "gender": "masculine", "number": "dual"},
    "ene":    {"case": "accusative",   "gender": "feminine",  "number": "dual"},
    "enAn":   {"case": "accusative",   "gender": "masculine", "number": "plural"},
    "enAs":   {"case": "accusative",   "gender": "feminine",  "number": "plural"},
    "enAni":  {"case": "accusative",   "gender": "neuter",    "number": "plural"},
    # ṭā — instrumental singular
    "enena":  {"case": "instrumental", "gender": "masculine", "number": "singular"},
    "enayA":  {"case": "instrumental", "gender": "feminine",  "number": "singular"},
    # os — genitive / locative dual
    "enayoH": {"case": "genitive",     "gender": "masculine", "number": "dual"},
    "enayos": {"case": "genitive",     "gender": "masculine", "number": "dual"},
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
    """Is this a word? Used by segmentation.

    The closed indeclinable class counts even when Vidyut's kosha has no entry — an avyaya IS a
    word, and treating it as unknown forces the segmenter to break it up. `kadAcana` ("ever") was
    being split into `kat` + `Acana` and glossed "to accumulate", which is what a reader actually
    hit on a Gītā line.
    """
    return (word_slp1 in PARTICLES
            or word_slp1 in UPASARGAS
            or word_slp1 in ENAD
            or _is_indeclinable(word_slp1)
            or bool(kosha().get(word_slp1)))


def _map_entry(entry) -> tuple[Analysis, bool, bool]:
    """Map a Vidyut PadaEntry → (Analysis, is_basic_noun, stem_gender_ok). Verbs count as 'basic'.

    `stem_gender_ok` answers: does this inflectional slot's gender agree with the gender the STEM
    actually has? A Sanskrit nominal stem carries an inherent gender — `sTAna` is neuter — and the
    kosha records it on the pratipadika as `lingas`. The per-entry `linga` is only the paradigm
    slot, and an ending like `-AnAm` fills the masculine, neuter AND feminine slots alike, so the
    slot cannot decide on its own. The stem can. Krdanta (participial) stems declare no lingas
    because they genuinely take any gender; those stay unranked rather than guessed at.
    """
    lakara = getattr(entry, "lakara", None)
    if lakara is not None:  # Tinanta (finite verb)
        features = {"tense": LAKARA.get(lakara, str(lakara))}
        # PRAYOGA (voice) decides which case carries which kāraka, so it must reach stage 4.
        # kartari: kartā → prathamā, karma → dvitīyā.  karmaṇi: karma → prathamā, kartā → tṛtīyā.
        # Without it the roles inverted on every passive sentence — silently, and confidently.
        if (pra := getattr(entry, "prayoga", None)) is not None:
            features["voice"] = "passive" if str(pra) == "karmaRi" else "active"
        # The GAṆA identifies WHICH root this is when several share a spelling. `kṛ` is two roots:
        # svādi *hiṃsāyām* "to kill" and tanādi *karaṇe* "to do". Without the class, the commonest
        # verb in Sanskrit gets glossed "to kill". The analysis knows it; the lookup needs it.
        de = getattr(entry, "dhatu_entry", None)
        if de is not None and getattr(de, "dhatu", None) is not None:
            gana = getattr(de.dhatu, "gana", None)
            if gana is not None:
                features["gana"] = str(gana)
        if (pur := getattr(entry, "purusha", None)) is not None:
            features["person"] = PURUSHA.get(pur, str(pur))
        if (vac := getattr(entry, "vacana", None)) is not None:
            features["number"] = VACANA.get(vac, str(vac))
        return Analysis(lemma=entry.lemma, pos="verb", features=features, raw_tags=["verb"]), True, True

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
    declared = list(getattr(pe, "lingas", None) or [])
    stem_gender_ok = not declared or linga in declared
    return Analysis(lemma=lemma, pos=pos, features=features, raw_tags=[]), is_basic, stem_gender_ok


#: Taddhita adverb endings that make a form avyaya by derivation, whatever else the lexicon lists.
#: 1.1.38 taddhitaś cāsarvavibhaktiḥ — a taddhita form that does not take the full set of case
#: endings is an avyaya. The `-tas` ablative adverbs (5.4.44 ff.) and the `-tra`/`-dā`/`-thā`
#: adverbs are exactly that: `tatas`, `atra`, `sarvadā`, `tathā` are indeclinable, full stop.
_AVYAYA_SUFFIX = ("tas", "tra", "dA", "TA")


def _is_indeclinable(word_slp1: str) -> bool:
    """Is this an avyaya? Read from the lexicon rather than hand-listed.

    Our PARTICLES dict covers ~30 words by hand; Vidyut flags avyayas across the whole lexicon, and
    541 tokens in the DCS sample that DCS calls indeclinable were missing from the hand list. Every
    one of those got inflected, took a case, and entered the kāraka graph as a spurious argument —
    the same failure as `na` being read as the noun `nā` ("navel"), just never finished.

    An avyaya is never inflected and never fills a kāraka role, so getting this wrong pollutes the
    semantic layer, not merely the tags. Two ways in, both grammatical:

      * the lexicon flags it avyaya AND offers no nominal reading — unambiguous, take it;
      * it is a taddhita adverb by derivation (1.1.38), which outranks a spurious nominal entry.
    """
    entries = kosha().get(word_slp1) or []
    if not entries:
        return False
    flagged = any(getattr(e, "is_avyaya", False) for e in entries)
    if not flagged:
        return False
    if word_slp1.endswith(_AVYAYA_SUFFIX):
        return True                        # the avyaya flag above already excludes patra/mitra/netra
    return not any(getattr(e, "vibhakti", None) is not None for e in entries)


#: SARVANĀMA — the pronominal stems Pāṇini lists at 1.1.27 (sarvādīni sarvanāmāni). A closed
#: class, so writing it down is transcription rather than a heuristic, exactly like the nipāta list.
#:
#: These decline irregularly and are among the commonest words in the language, yet the lexicon
#: also carries obscure homographs — `tA`, `ta` — that beat them on an alphabetical tie-break. `te`
#: ("your", "they") was coming back as `tA`, a rare feminine noun, purely because `A` sorts before
#: `d` in ASCII.
#: The PERSONAL pronouns, a privileged subclass within the sarvādi gaṇa. Pāṇini names them
#: individually because the verb's puruṣa is chosen by them: 1.4.105 `yuṣmady upapade samānā-
#: dhikaraṇe sthāniny api madhyamaḥ` (with yuṣmad → madhyama-puruṣa) and 1.4.107 `asmady uttamaḥ`
#: (with asmad → uttama-puruṣa). Nothing else in the gaṇa governs agreement that way.
#:
#: MEASURED AND NOT USED AS A RANK. Promoting these above the rest of the gaṇa fixes `tvam`,
#: `tvām`, `tvayā` and `mayi`, which are unambiguous — but it costs more than it gains, because
#: `te` is far more frequent and genuinely contested between `tad` ("they", "his") and `yuṣmad`
#: ("to you"), and a fixed rank decides that ambiguity the same way every time. Measured: sūtra
#: lemma 88.7 -> 87.7, kāvya 74.7 -> 74.6, śāstra 79.9 -> 79.8, nothing improved.
#:
#: Kept as a named class because the distinction is real and a context-sensitive rule may want it;
#: what does not work is using it as a static preference.
PERSONAL_PRONOUNS: frozenset[str] = frozenset({"asmad", "yuzmad", "mad", "tvad"})

SARVANAMA: frozenset[str] = frozenset("""
tad yad etad idam adas kim tyad yuzmad asmad Bavat
sarva viSva uBa uBaya anya anyatara itara tva nema sama sima
pUrva para avara dakziRa uttara apara aDara sva antara eka
""".split())


from functools import lru_cache


@lru_cache(maxsize=1)
def _attested_lemmas() -> frozenset[str]:
    """Lemmas a READER's dictionary records — Apte, Macdonell, or our curated seed.

    Monier-Williams is comprehensive to a fault: it carries inflected forms as headwords in their
    own right, so `karmaRi` (the locative of `karman`) and `tA` (a rare feminine beside the pronoun
    `tad`) look like ordinary lemmas and win on an alphabetical tie-break. Apte and Macdonell were
    compiled for people reading texts and do not list those, which makes attestation a clean signal.

    It is also independent of DCS, so using it does not contaminate the benchmark we measure with.
    """
    import sqlite3
    from pathlib import Path
    db = Path(__file__).resolve().parent.parent / "knowledge" / "sanskrit.db"
    if not db.exists():
        return frozenset()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT DISTINCT lemma FROM sense WHERE source IN ('apte','macdonell','seed')"
        ).fetchall()
    except sqlite3.Error:
        return frozenset()
    finally:
        conn.close()
    return frozenset(r[0] for r in rows)


#: VEDIC → CLASSICAL correspondences, applied ONLY when a form is otherwise unanalysable.
#:
#: The kosha is built on the classical language, so ordinary Vedic wordforms come back POS-unknown
#: and take no case at all — 624 tokens in a 9,092-token Ṛgveda/Atharvaveda sample. These are not
#: rare words: `devāsaḥ` ("the gods") occurs 11 times and `devebhiḥ` 28. Their classical
#: equivalents `devāḥ` and `devaiḥ` resolve perfectly, so this is a dialect gap, not a lexicon one.
#:
#: Each correspondence is a stated rule of the grammar, not a shape observed in the corpus:
#:
#:   7.1.50 `āj jaser asuk` — after ā, the nominative-plural ending `jas` takes the augment
#:          `asuk`, giving Vedic `devāsaḥ` where the classical language has `devāḥ`.
#:   7.1.9  `ato bhisa ais` — after an a-stem, `bhis` is REPLACED by `ais`. Vedic simply does not
#:          apply the replacement, so it keeps `devebhiḥ` where classical has `devaiḥ`.
#:
#: The anunāsika is separate: DCS writes the Vedic nasalised vowel with ṁ (U+1E41), which is not
#: SLP1 at all, so those forms could never have been looked up. It corresponds to classical `n` —
#: `devām̐` is the accusative plural `devān`, `mahām̐` the nominative singular `mahān`. Note this
#: is NOT the anusvāra: ISO 15919 also writes ṁ for anusvāra, and `normalize.py` maps it to ṃ for
#: ISO input. The two conventions collide on one character, which is why this fix lives here — at
#: kosha lookup, where the surrounding form disambiguates — and not in global normalisation.
#:
#: Verified before use: every correspondence below was checked to return the case AND number the
#: DCS gold annotation records, not merely to return something.
#: Targets are the KOSHA-FACING (pre-visarga) forms. Mapping `devāsaḥ` to `devāḥ` looks right and
#: fails, because the kosha keys on `devās` and rejects the visarga — the same distinction
#: `to_pausa` exists for on the display side. Written form vs lookup form, one more time.
_VEDIC_ENDINGS = (
    ("AsaH", "As"), ("Asas", "As"),      # 7.1.50 — nom./voc. pl. of a-stems
    ("eBiH", "Es"),  ("eBis", "Es"),     # 7.1.9  — instr. pl. of a-stems
)
_VEDIC_ANUNASIKA = "\u1e41"             # ṁ, the nasalised vowel — classical `n`


def _classical_equivalent(word_slp1: str) -> str | None:
    """The classical form of a Vedic wordform, or None if nothing applies."""
    if _VEDIC_ANUNASIKA in word_slp1:
        return word_slp1.replace(_VEDIC_ANUNASIKA, "n")
    for vedic, classical in _VEDIC_ENDINGS:
        if word_slp1.endswith(vedic) and len(word_slp1) > len(vedic) + 1:
            return word_slp1[:-len(vedic)] + classical
    return None


def analyze_candidates(word_slp1: str) -> list[Analysis]:
    """All morphological readings of a word, deduped and in a DETERMINISTIC order.

    Prefers Basic (non-kṛdanta) noun readings so headwords stay clean, then dedupes Vidyut's many
    paradigm-slot repeats. Picking one reading per token is disambiguation's job.
    """
    if word_slp1 in PARTICLES or _is_indeclinable(word_slp1):
        return [Analysis(lemma=word_slp1, pos="particle",
                         features={}, raw_tags=["indeclinable"])]
    if word_slp1 in ENAD:
        # A pronoun with real case/number/gender — not a particle. 2.4.34 restricts which slots
        # exist, so the paradigm is partial by rule rather than by omission.
        return [Analysis(lemma="etad", pos="noun",
                         features=dict(ENAD[word_slp1]), raw_tags=["sarvanAma", "enad"])]
    if word_slp1 in UPASARGAS:
        # No case, no number: an upasarga is avyaya, so it cannot become a kāraka argument.
        return [Analysis(lemma=word_slp1, pos="upasarga",
                         features={}, raw_tags=["upasarga", "indeclinable"])]
    entries = kosha().get(word_slp1) or []
    if not entries:
        # Vedic wordform? Ask again in the classical language the kosha actually knows. The
        # recursion terminates because `_classical_equivalent` returns None for classical forms.
        classical = _classical_equivalent(word_slp1)
        if classical and classical != word_slp1:
            alt = analyze_candidates(classical)
            if alt and alt[0].pos != "unknown":
                return alt
        return [Analysis(lemma=word_slp1, pos="unknown", features={}, raw_tags=[])]

    mapped = [_map_entry(e) for e in entries]
    has_basic_noun = any(is_basic and a.pos == "noun" for a, is_basic, _ in mapped)

    seen: set[tuple] = set()
    ranked: list[tuple[Analysis, bool]] = []
    for a, is_basic, stem_gender_ok in mapped:
        # drop deep-root (kṛdanta) noun readings when a clean Basic reading exists for this word
        if a.pos == "noun" and not is_basic and has_basic_noun:
            continue
        key = (a.pos, a.lemma, a.features.get("case", ""), a.features.get("number", ""),
               a.features.get("gender", ""), a.features.get("tense", ""), a.features.get("person", ""))
        if key in seen:
            continue
        seen.add(key)
        ranked.append((a, stem_gender_ok))

    # Gender used to fall out of ALPHABETICAL order ("feminine" < "masculine" < "neuter"), which is
    # arbitrary. Agreement with the stem's own declared gender is the deterministic signal.
    #
    # The LEMMA key carried the same alphabetical accident, and it hid longer because nothing
    # measured lemma-vs-lemma ties. SLP1 writes long vowels as capitals and ASCII sorts capitals
    # first, so `devA` beat `deva` and `karmaRi` beat `karman` on every tie — the a-stem lost to
    # its own ā-stem homograph purely on byte order. That was 20.7% of all high-confidence errors.
    # Stem-gender agreement therefore outranks the lemma string: linguistic signal before ASCII.
    # 1.1.27 sarvādīni sarvanāmāni names a CLOSED, privileged class, so a pronominal stem outranks
    # an obscure homograph — and that has to be decided BEFORE case, not after it.
    #
    # Case was sorted alphabetically, which is not a linguistic fact about anything: "accusative"
    # simply precedes "nominative" in ASCII, so every accusative reading sorted ahead of every
    # nominative one and the sarvanāma preference below never got to vote. `vayam` ("we", nom. pl.
    # of asmad) lost to `vaya`, a rare noun meaning "food", purely on byte order — 144 times in the
    # Ṛgveda sample. `tvam` lost to `tva`, `aham` to `aha`, `sa` to `sā`. `mām` came out right only
    # because its correct reading happens to be accusative too.
    #
    # These forms are SUPPLETIVE — `vayam` contains no trace of the stem `asmad` — so no
    # string-matching heuristic could have recovered them; only the class membership can.
    ranked.sort(key=lambda pair: (pair[0].pos,
                                  0 if pair[0].lemma.split("#")[0] in SARVANAMA else 1,
                                  pair[0].features.get("case", ""),
                                  0 if pair[1] else 1,
                                  pair[0].lemma,
                                  pair[0].features.get("number", ""),
                                  pair[0].features.get("gender", "")))
    out = [a for a, _ in ranked]
    # Drop readings whose lemma no reader's dictionary records, but only when a recorded one
    # survives — never leave a word with nothing. This is what stops `karmaRi` (an inflected form
    # MW carries as a headword) from beating `karman`.
    attested = _attested_lemmas()
    if attested:
        keep = [a for a in out if a.lemma.split("#")[0] in attested or a.pos not in ("noun", "verb")]
        if keep:
            return keep
    return out
