# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Bulk-ingest Monier-Williams into the dictionary's `sense` table (source='MW').

Source: the Cologne Digital Sanskrit Dictionaries' Monier-Williams, as the ready-made
`lookup/mw.tsv` from github.com/tokushige-koyasan/cdsl-corpus — a processed form of
github.com/sanskrit-lexicon/MWS. Its `headword_slp1` column already matches our engine lemmas,
so no transliteration is needed; we only strip the Cologne body markup.

Data © the Cologne Digital Sanskrit Dictionaries; digitization layer CC-BY-SA-4.0; the MW text
itself is public domain. Attribute Cologne + sanskrit-lexicon/MWS.

    python -m knowledge.ingest_mw          # download (cached) + load all of MW
"""
from __future__ import annotations

import html
import re
import sqlite3
import urllib.request
from pathlib import Path

from .dictionary import _DB, ensure_schema
from .quality import Reconciler, classify_rejection

_HERE = Path(__file__).resolve().parent
_CACHE = _HERE / "mw.tsv"
_URL = "https://raw.githubusercontent.com/tokushige-koyasan/cdsl-corpus/main/lookup/mw.tsv"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_GLOSS_CAP = 600  # keep display sane

# --- scholarly noise ---------------------------------------------------------------------
# MW entries open with the accented headword + grammar markers + an etymology bracket, and close
# with source citations. All of that is unreadable to a learner and, worse, crowds out the actual
# meaning when several senses are shown together. Some "senses" are pure cross-references
# ("yoga &c. See pp. 856, 858.") and carry no meaning at all — those are dropped.
_CITE = (r"(?:RV|AV|ŚBr|SBr|Br|MBh|Pur|Hcat|Kauś|Mn|Yājñ|VarBṛS|Rājat|Kāv|Pañcat|Hariv|Up|GṛS"
         r"|TāṇḍyaBr|VP|Ragh|Kum|Uṇ|Dhātup|Vikr|AitBr|VPrāt|Sch|ib|L|W|T|Gaut|Āpast|Kathās|BhP"
         r"|Suśr|Car|Nir|Pāṇ|Śiś|Naiṣ|Vet|Prab)")
_GRAM = (r"(?:mf\([^)]*\)n\.|mfn\.|m\.|n\.|f\.|ind\.|cl\.\s*\d+\.?(?:\s*[PĀ]\.)*"
         r"|Nom\.|pl\.|sg\.|du\.)")
_BRACKET = r"\((?:[^()]|\([^()]*\))*\)"          # tolerates one nesting level
_STUB = re.compile(r"^\s*[^,]{0,25}\s*&?c?\.?\s*[Ss]ee\s+(pp?\.|\S+)", re.I)
# Verb headword entries whose "sense" is a conjugation table (forms, not meaning):
#   "vad cl. 1. P. Ā. (Dhātup. xxiii, 40) va/dati, ˚te (… Pot. udeyam …; pf. uvAda …)"
_CONJ = re.compile(r"Dhātup\.|\bcl\.\s*\d+\.?\s*[PĀ]\.|\b(?:pf|aor|Pot|impf|Cond)\.\s")
# Unparsed Cologne artifacts ("{{Lbody=196110}}") and pure grammar dumps (the `idam` entry is a
# page of pronominal paradigms). Neither is a meaning.
_JUNK = re.compile(r"\{\{|pronom\.\s*base|g\.\s*sarvAdi|see\s+Gr\.\s*\d")
# Entries that point elsewhere instead of giving a meaning ("the root ji, Pāṇ. i, 4, 26").
_XREF = re.compile(r"^\s*(?:the\s+root\b|=\s|for\s+\S+\s*[,(]|cf\.\s)", re.I)
# A leading scholarly bracket, e.g. "[in RV. seven times a/sat …] not being, not existing".
_LEAD_BRACKET = re.compile(r"^\s*\[[^\]]*\]\s*")
# Parentheticals that are pure apparatus rather than meaning.
_PAREN_NOISE = re.compile(r"\s*\((?:[^()]|\([^()]*\))*?(?:cf\.|q\.v\.|ifc\b|superl\.|Pāṇ\.|see\s)"
                          r"(?:[^()]|\([^()]*\))*\)")
# Citations anywhere, not just at the end: ", KaṭhUp", ", RV.; KauṣUp".
_CITE_ANY = re.compile(rf"[,;]\s*\b{_CITE}\b\.?")
# Generic trailing-citation stripper. Enumerating MW's abbreviations is endless (KaṭhUp, ŚvetUp,
# KātyŚr, RPrāt …), so match the SHAPE instead: capitalised abbreviations and "vii, 56, 8" style
# references at the end of a gloss. Roman numerals must be followed by digits, or the pattern eats
# the tail of ordinary words ("unrea/l/", "te/ll/").
_U = "ĀāĪīŪūṚṛṜṝḶḷṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃ"
_TRAIL_CITE = re.compile(
    rf"(?:[,;]?\s*(?:&\s*c\.?|\b[A-Z{_U}][A-Za-z{_U}]*\.?"
    rf"|\b[ivxlc]{{1,6}}\s*,\s*\d+(?:\s*,\s*\d+)*)[.;]?\s*)+$")


# A capitalised final token is ambiguous: "MBh." is a citation, but "Śiva." is the MEANING
# ("N. of Śiva"). Stripping blindly gutted ~1,700 entries down to a dangling "N. of". So a strip is
# rejected whenever it would leave the gloss ending on a function word — the tell that what
# followed was the actual referent, not a source.
_DANGLING = re.compile(r"\b(?:of|a|an|the|or|and|in|by|from|to|with|for|as|on|at)$", re.I)


def _strip_trailing_cites(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        candidate = _TRAIL_CITE.sub("", text).strip(" ,;.")
        if not candidate or _DANGLING.search(candidate):
            break                                   # the "citation" was the meaning — keep it
        text = candidate
    return text
_TAIL = re.compile(rf"[,;]?\s*\b{_CITE}\b\.?(?:\s*&c\.)*(?:\s*[ivxlcIVXLC]+[,\s\d]*)*\s*$")


# --- deeper apparatus stripping -------------------------------------------------------------
# 17% of MW glosses carry scholarly shorthand and 14% grammatical apparatus, almost always wrapped
# AROUND a real meaning ("a-fRin mfn. free from debt" → "free from debt"). So these strip the
# wrapper rather than dropping the entry. Every pattern was checked against a fixture set that
# includes clean glosses which must survive untouched.
_U2 = "ĀāĪīŪūṚṛṜṝḶḷṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃ"
_W2 = rf"[A-Za-z{_U2}˚/'’—\-]+"
_GRAM2 = r"(?:mf\([^)]*\)n\.|mfn\.|[mnf]\.|ind\.|du\.|pl\.|sg\.|Nom\.)"
_LEAD_NUM = re.compile(r"^\s*\(\s*[\dA-Za-z/˚]{1,4}\s*\)\s*")             # "(3) ", "(u/), "
_LEAD_HEAD2 = re.compile(rf"^\s*{_W2}(?:\s*(?:[—-]|or|,)\s*{_W2})*\s*,?\s*(?=(?:{_GRAM2}|-?√))")
_LEAD_ROOTWORD = re.compile(rf"^\s*(?=\S*[AIUfxMHKGCJWQRTDPBSz]){_W2}\s+(?=to\s)")
_LEAD_ROOT2 = re.compile(r"^\s*-?√\s*\S+\s*")
_LEAD_GRAM2 = re.compile(rf"^\s*(?:{_GRAM2}\s*)+")
_BRACKET_ANY = re.compile(r"\s*\[[^\]]*\]")
_ETYM_PAREN = re.compile(r"\s*\((?:[^()]|\([^()]*\))*?"
                         r"(?:Gk\.|Lat\.|Goth\.|Germ\.|Eng\.|Zd\.|conjecturable|cf\.)"
                         r"(?:[^()]|\([^()]*\))*\)")
_DIGIT_TAIL = re.compile(r"[,;]?\s*(?:\b[ivxlc]{1,6}\b[,\s]*)?\d+(?:\s*[-–]\s*\d+)?"
                         r"(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*\s*$")
_QUOTE2 = re.compile(r'\s*["“”]\s*')


def _strip_apparatus(text: str) -> str:
    for _ in range(3):
        text = re.sub(r"^[\s,;:]+", "", text)
        text = _LEAD_NUM.sub("", text)
        text = _LEAD_ROOTWORD.sub("", text)
        text = _LEAD_HEAD2.sub("", text)
        text = _LEAD_ROOT2.sub("", text)
        text = _LEAD_GRAM2.sub("", text)
    text = _BRACKET_ANY.sub("", text)
    text = _ETYM_PAREN.sub("", text)
    text = _QUOTE2.sub(" ", text)
    for _ in range(3):
        nxt = _DIGIT_TAIL.sub("", text).strip(" ,;:.")
        if nxt == text:
            break
        text = nxt
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:.-")


#: MW glosses a verb root with an English infinitive — "to go", "to come forth". That is the
#: reliable boundary between the conjugation apparatus and the actual meaning.
_DEFN_START = re.compile(r"\bto\s+[a-z]{3,}")


def clean_gloss(gloss: str) -> str | None:
    """Strip MW apparatus down to the meaning. Returns None for cross-reference stubs."""
    if not gloss or _STUB.match(gloss) or _JUNK.search(gloss):
        return None
    if _CONJ.search(gloss):
        # A conjugation table is not a meaning — but most verb entries STATE the conjugation and
        # then define the root, and rejecting the whole entry threw away 1,260 real definitions.
        # `anugam`, `Agam`, `udgam`, `saMgam` had no dictionary entry at all as a result, so every
        # prefixed verb built on them showed the reader nothing and lowered the engine's own
        # confidence. Salvage from the first infinitive; reject only if there is no definition.
        match = _DEFN_START.search(gloss)
        if not match:
            return None
        gloss = gloss[match.start():]
    if _XREF.match(gloss):
        return None
    gloss = _LEAD_BRACKET.sub("", gloss)
    gloss = _PAREN_NOISE.sub("", gloss)
    gloss = _CITE_ANY.sub("", gloss)
    gloss = _strip_trailing_cites(gloss)
    gloss = _strip_apparatus(gloss)
    s = re.sub(r"^\d+\.\s*", "", gloss)
    s = re.sub(r"^\S*/\S*\s*", "", s)                       # accented headword, e.g. "mu/ni "
    s = re.sub(rf"^[A-Za-zĀāĪīŪūṚṛṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃ]+\s+(?={_GRAM})", "", s)  # plain headword
    for _ in range(4):
        s = re.sub(rf"^{_GRAM}\s*", "", s)
        s = re.sub(rf"^{_BRACKET}\s*",
                   lambda m: "" if re.search(r"√|fr\.|accord|prob|q\.v\.|ifc|rarely", m.group()) else m.group(),
                   s, count=1)
    for _ in range(6):                                        # citation chains: ", RV.; AV.; Br."
        nxt = _TAIL.sub("", s).strip()
        nxt = re.sub(r"\s*&c\.(\s*&c\.)*\s*$", "", nxt).strip(" ,;:.")
        if nxt == s:
            break
        s = nxt
    s = re.sub(r"^[,;:\s]+", "", s).strip(" ,;:.")
    return s if len(s) > 3 else None


def _clean(body: str) -> str:
    """Cologne body markup → readable gloss: drop tags (keep inner text), unescape, tidy."""
    t = _TAG.sub("", body).replace("¦", " ")
    t = html.unescape(t)
    t = _WS.sub(" ", t).strip().strip('"').strip()
    return t


def _download() -> None:
    if _CACHE.exists() and _CACHE.stat().st_size > 1_000_000:
        return
    print(f"downloading MW (~44 MB) → {_CACHE.name} ...")
    urllib.request.urlretrieve(_URL, _CACHE)


def ingest(limit: int | None = None) -> int:
    """Load MW into `sense` (source='MW'), one row per dictionary entry. Returns row count."""
    _download()
    conn = sqlite3.connect(_DB)
    try:
        ensure_schema(conn)
        conn.execute("DELETE FROM sense WHERE source = 'MW'")

        rec = Reconciler("MW")
        rows: list[tuple[str, str, str, str | None]] = []
        cur_key = cur_lemma = None
        buf: list[str] = []
        n_entries = 0

        def flush():
            if not (cur_lemma and buf):
                return
            rec.seen()
            raw = _clean(" ".join(buf))
            gloss = clean_gloss(raw)
            if gloss:
                gloss = clean_for_reading(gloss)          # asides, citations, shorthand
            if gloss:                                     # a purely parenthetical entry is now empty
                rows.append((cur_lemma, "MW", gloss[:_GLOSS_CAP], gender_of(" ".join(buf))))
                rec.kept()
            else:
                rec.reject(raw, classify_rejection(raw, gloss or ""), cur_lemma)

        with _CACHE.open(encoding="utf-8") as f:
            f.readline()  # header
            for line in f:
                parts = line.rstrip("\n").split("\t", 4)
                if len(parts) < 5:
                    continue
                _iast, slp1, entry_id, _page, body = parts
                key = (slp1, entry_id.split(".")[0])  # group main entry + its continuation lines
                if key != cur_key:
                    flush()
                    if limit and n_entries >= limit:
                        break
                    cur_key, cur_lemma, buf = key, slp1, []
                    n_entries += 1
                buf.append(body)
            else:
                flush()

        rec.check()
        conn.executemany(
            "INSERT INTO sense (lemma, source, gloss, gender) VALUES (?, ?, ?, ?)", rows)
        rec.record(conn, origin=_URL, path=_CACHE)
        conn.commit()
        print("  " + rec.summary())
        return len(rows)
    finally:
        conn.close()


# ── reading pass ────────────────────────────────────────────────────────────────────────────────
# `clean_gloss` above strips MW's structural apparatus. This second pass removes what is left over
# for a READER: parenthetical asides (24.1% of glosses carry one, often an encyclopaedia entry
# about Rāvaṇa's brothers), verse citations, and shorthand marks. Reported by the person actually
# using the engine on their own texts for two days, which no benchmark here surfaced.
_R_PARENS = re.compile(r"\s*\([^()]*(?:\([^()]*\)[^()]*)*\)")   # tolerates one nesting level
_R_CITES = re.compile(r"\b[ivxlcIVXLC]+,\s*\d+(?:,\s*\d+)*")     # "i, 50, 10"
_R_NUMDOT = re.compile(r"\b\d+\.\s*")
_R_ETC = re.compile(r"\s*&c\.(\s*&c\.)*")
#: Cologne's brace constructs — column markers `{c10c}`, run-on headword bits `{@-tā,@}`, and the
#: empty `{ }` left where a Sanskrit span was removed. 43,425 glosses carried one, almost all from
#: Apte and Macdonell, because the MW cleaner never had to know about them.
_R_BRACE = re.compile(r"\{[^{}]*\}")
#: MW states each sense's gender in a <lex> tag — m. 63,888, mfn. 50,738, n. 33,666, f. 31,341,
#: 62.7% of all entries. The reading pass strips it as apparatus, which is right for the GLOSS and
#: wrong for the record: it is the one signal that separates homonymous nominal stems.
_R_LEX_GENDER = re.compile(r"<lex[^>]*>\s*(mfn|mf|m|f|n)\s*\.?\s*</lex>")
_GENDER_TAG = {"m": "masculine", "f": "feminine", "n": "neuter", "mfn": "any", "mf": "any"}


def gender_of(raw_body: str) -> str | None:
    """The gender MW assigns this sense, before any cleaning. `mfn.` means adjectival — it agrees
    with whatever it qualifies, so it matches ANY gender rather than none."""
    m = _R_LEX_GENDER.search(raw_body)
    return _GENDER_TAG.get(m.group(1)) if m else None
_R_SHORTHAND = re.compile(r"[˚√]")
_R_DIGITS = re.compile(r"\s*\b\d+\b")
#: MW / Apte / Macdonell abbreviations — an ENUMERATED list, because neither shape nor frequency
#: can separate an abbreviation from a word.
#:
#: The pattern below used to strip any capitalised token of <=10 letters before a period, and it
#: was deleting meaning: `Going.` `Wealth.` `Fire.` became empty glosses outright (313 one-word
#: Apte senses died), and `the god Indra.` was silently truncated to `the god`. Profiling found
#: 4,046 distinct such tokens, of which 10,135 occurrences sit in a long tail — `Revival`,
#: `Foulness`, `Autumnal`, `Invocation` — every one an ordinary English word ending a sentence.
#:
#: Frequency is no better a discriminator than shape: `Śiva` (981), `Viṣṇu` (657) and `Indra` (342)
#: are as common as the real citations and are the whole point of the gloss.
#:
#: So the logic is inverted: a MULTI-letter token is stripped only if it is named here. A lone
#: capital (`P.` `Ā.` `V.`) is apparatus by construction — no English gloss is one letter long.
_STRIP_ABBREV = frozenset("""
Ved Comp Caus Den Desid Intens Nom Pass Perf Fut Aor Impv Opt Pot Subj
RV AV SV YV Br MBh Rām Kāv Śak Ragh Ku Me Māl Mu Ve Bh Pt Ms Bg Bhāg Hariv
Kāś Sk Vop Pāṇ Ait Ch Kaṭh Muṇḍ Praśn Taitt Śat Gaut Āp Baudh Mn Yāj Nir
Rhet Gram Log Phil Math Astr Med Mus Dr Mar Hind Pers Gr Lat Zd
Cf cf esp ib id sc lit fig opp Ved Vedic Class Later Nom
""".split())

#: A lone capital letter followed by a period is always apparatus (P. = parasmaipada, Ā. =
#: ātmanepada, V. = Veda). `N.` is the exception and means "name of" — 46,910 occurrences.
_R_ABBREV_SOLO = re.compile(r"\b([A-ZĀŚṢṚ])\.")
_R_ABBREV = re.compile(r"\b([A-ZĀŚṢṚ][A-Za-zĀāĪīŪūŚśṢṣṚṛṆṇḌḍṬṭḤḥṂṃ]{1,9})\.")
#: MW's gender / part-of-speech markers. `mfn.` is "masculine feminine neuter" — it marks an
#: ADJECTIVE, which is grammar, not meaning, and our morphology layer already knows the gender.
#: These are lowercase, so the capital-initial abbreviation strip above sailed straight past them.
_R_POS = re.compile(r"\b(?:mfn|mf\([^)]*\)n|m|f|n|ind|nom|acc|abl|gen|loc|voc|du|pl|sg)\.")
#: MW prints the headword before the definition, joined by an em dash for compounds — `sa—rAjan`.
#: Echoing the word back at the reader is not a gloss.
_R_HEADWORD = re.compile(r"^\s*\S*—\S*\s+")

#: `= X` is a CROSS-REFERENCE, not a definition: "= a-kAma" means "see a-kāma". 7,770 glosses are
#: nothing but this, and a reader shown "= a-kAma" has been told nothing. Where the whole gloss is
#: `X = Y` it is dropped; where real prose surrounds it, only the reference clause goes.
_R_XREF_ONLY = re.compile(r"^\s*(?:\S+\s*)?=\s*\S+")
_R_XREF_CLAUSE = re.compile(r"\s*=\s*\S+")
_R_XREF_TAIL = re.compile(r"\s*\b(?:above|below|next|ib)\b\s*$", re.I)

#: `?` marks an uncertain reading at the EDGES of a gloss ("? indigestion"). Mid-gloss it is real
#: punctuation — "how else? what else?" is the actual meaning of an interrogative — so only the
#: leading and trailing marks are removed.
_R_QUERY = re.compile(r"^\s*\?\s*|\s*\?\s*$")
_R_TIDY = re.compile(r"\s{2,}")

# ── conventions the OTHER dictionaries use ──────────────────────────────────────────────────────
# This pass was written against Monier-Williams and is only 0.8% dirty there. Apte and Macdonell
# call the same function, and each has its OWN apparatus vocabulary that MW never uses — so 11.3%
# of Apte and 16.8% of Macdonell reach the reader with grammar-speak still attached. Because
# Macdonell outranks MW in source authority, its junk actively BEATS a clean MW gloss: `tasmāt` is
# stored as ") ad. therefore ." even though MW says "from that, on that account, therefore".
#
# Deliberately NOT applied to the Dhātupāṭha: it never calls this function, and its trailing
# `(√kṛ, karaṇe, tanādi)` is the root citation we add on purpose, not stray apparatus.

#: Macdonell abbreviates the cases differently from MW — `nm.` where MW writes `nom.`, `ac.` for
#: accusative, `lc.` locative, `in.` instrumental, `ab.` ablative. Only the two-letter forms are
#: listed: single letters (`d.` dative, `g.` genitive) are too easily ordinary text to strip safely.
_R_MD_CASE = re.compile(r"\b(?:nm|ac|ab|lc|in)\.\s*")
#: `ad.` is Macdonell's "adverb" and `pp.`/`p. p.` its "past participle" — both grammar, not meaning.
_R_MD_POS = re.compile(r"\b(?:p\.\s?p\.|pp\.|ad\.)\s*")
#: Left where a Sanskrit span was cut out; `[Page223- ]` is a scan artefact from the printed page.
_R_ANGLE = re.compile(r"\s*[〈〉⟨⟩]\s*")
_R_PAGE = re.compile(r"\s*\[\s*Page[^\]]*\]\s*")
#: `[ ]` left where a Sanskrit span was cut ("adv. [ ]"). Brackets WITH text hold etymology
#: ("[leading beyond: pṛ]") and are kept — stripping those loses the sense, not apparatus.
_R_EMPTY_BRACKET = re.compile(r"\s*\[\s*\]\s*")
#: Macdonell prints the headword, then its POS, then the sense: `a-kīrtita, pp. unmentioned.`
#: Macdonell marks the Vedic accent with an acute — `sanná`, `bhará` — and those characters were
#: missing from the class, so the echo survived as "sanná, sunk down etc." The POS lookahead is
#: what keeps this safe and is deliberately retained: without it the pattern also matches real
#: glosses like "Prakṛti, Māyā, Illusion" and eats the first sense. Measured: 651 glosses match
#: on the accent alone, and the sampled ones were overwhelmingly legitimate.
_R_MD_HEADWORD = re.compile(
    r"^\s*[A-Za-zĀāĪīŪūṚṛŚśṢṣṆṇḌḍṬṭḤḥṂṃáéíóúŕṝ\u0301-]+,\s*(?=(?:p\.\s?p\.|pp|ad|a|mfn)\.)")
#: A gloss ending " ." or "; ." — the sense was dropped and its punctuation left behind ("bee .").
_R_DANGLING_END = re.compile(r"[\s;:,]+[.,]\s*$")
_R_DANGLING_EDGE = re.compile(r"^\s*[)\]}]\s*|\s*[(\[{]\s*$")

#: Abbreviations that carry MEANING, not provenance. `N.` alone appears 46,910 times and means
#: "name of" — stripping it as though it were a citation destroys the sense, which is exactly the
#: mistake that once turned "N. of Śiva" into "N. of". Grammatical markers stay because they
#: distinguish one sense of a verb from another.
_KEEP_ABBREV = {"P", "Ā", "Caus", "Pass", "Desid", "Intens", "Nom", "ifc", "esp", "cf"}


#: A "gloss" that is only the headword plus a gender marker — `tA f`, `akzaka m` — states no
#: meaning at all. 3,606 of these were being shown to the reader as if they were definitions.
#: Returning nothing is honest: the word then reports no meaning found, rather than pretending.
_R_ECHO = re.compile(r"^\s*[^\s]{1,16}\s+(?:mfn|ind|m|f|n)\s*\.?\s*$")
_R_NOTHING = frozenset({"id", "ib", "m", "f", "n", "mfn", "ind", "do", "the same"})


def clean_for_reading(gloss: str) -> str:
    """Strip what a reader does not want: asides, citations, shorthand. Meaning is preserved."""
    if not gloss:
        return gloss
    text = _R_PARENS.sub(" ", gloss)
    text = _R_CITES.sub(" ", text)
    text = _R_NUMDOT.sub(" ", text)
    text = _R_ETC.sub(" ", text)
    text = _R_ABBREV_SOLO.sub(
        lambda m: "name of" if m.group(1) == "N" else
                  (m.group(0) if m.group(1) in _KEEP_ABBREV else " "), text)
    text = _R_ABBREV.sub(
        lambda m: " " if (m.group(1) in _STRIP_ABBREV
                          and m.group(1) not in _KEEP_ABBREV) else m.group(0),
        text,
    )
    text = _R_BRACE.sub(" ", text)
    text = _R_HEADWORD.sub("", text)
    if _R_XREF_ONLY.match(text):
        remainder = _R_XREF_TAIL.sub("", _R_XREF_ONLY.sub("", text)).strip(" ;,:-")
        if len(remainder) < 4:
            return ""                                        # the whole gloss was a pointer
        text = remainder
    text = _R_XREF_CLAUSE.sub(" ", text)
    text = _R_QUERY.sub("", text)
    text = _R_POS.sub(" ", text)
    text = _R_SHORTHAND.sub("", text)
    text = _R_DIGITS.sub(" ", text)
    text = _R_PAGE.sub(" ", text)
    text = _R_EMPTY_BRACKET.sub(" ", text)
    text = _R_ANGLE.sub(" ", text)
    text = _R_MD_HEADWORD.sub("", text)
    text = _R_MD_CASE.sub(" ", text)
    text = _R_MD_POS.sub(" ", text)
    text = _R_TIDY.sub(" ", text)
    text = _R_DANGLING_EDGE.sub("", text)
    text = _R_DANGLING_END.sub("", text)
    text = re.sub(r"\s+([;,:])", r"\1", text)
    text = re.sub(r"(name of)\s+of\b", r"\1", text)          # "N. of X" must not double up
    text = text.strip(" ;,:-")
    if _R_ECHO.match(text) or text.strip(" .").lower() in _R_NOTHING:
        return ""                                             # no meaning stated — say so honestly
    return text


if __name__ == "__main__":
    print(f"ingested {ingest():,} Monier-Williams entries")
