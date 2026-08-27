# Knowledge & retrieval layer (Stage 3)

The "meaning is retrieved" half of the architecture. Two stores, per ARCHITECTURE.md:

- **Symbolic** (this, now) — exact dictionary lookup by lemma. Deterministic, no ML. SQLite.
- **Vector** (next) — semantic retrieval of commentary/translations for the deeper *essence*
  (Qdrant + BGE-M3 hybrid). Not built yet.

## Symbolic dictionary — current state

`dictionary.py` builds a SQLite table `sense(lemma, source, gloss)` and exposes:
- `lookup(lemma) -> list[Sense]`
- `attach_senses(parse_result)` — fills each token's `.senses`

Two sources populate the same table:
- **`source="seed"`** — `dictionary.yaml`, concise curated glosses for the gold vocabulary.
  Rebuild with `python -m knowledge.dictionary`.
- **`source="MW"`** — the full Monier-Williams (**279k entries**), loaded by
  `python -m knowledge.ingest_mw`.

`lookup()` returns **seed first** (concise, for common words), then MW (comprehensive) — so common
words read cleanly and rare words still resolve. The DB (`sanskrit.db`) and the MW cache
(`mw.tsv`) are generated/gitignored.

## Monier-Williams ingestion — DONE

`ingest_mw.py` loads MW from the ready-made **`lookup/mw.tsv`** in
[`tokushige-koyasan/cdsl-corpus`](https://github.com/tokushige-koyasan/cdsl-corpus) — a processed
form of [`sanskrit-lexicon/MWS`](https://github.com/sanskrit-lexicon/MWS) (the Cologne
digitization). Its `headword_slp1` column already matches our engine lemmas, so no transliteration
is needed; we only strip the Cologne body markup and group each entry's continuation lines.

**Why this source over the raw `sanskrit-lexicon/MWS` repo:** same underlying data, but already
split into an SLP1-keyed TSV — far less parsing. (The Cologne server `pycdsl` uses was unreachable
from the build environment; GitHub-raw is.)

**Licensing:** MW text is public domain; the Cologne digitization layer is CC-BY-SA-4.0 — both
compatible with this project's open, non-commercial stance (PRD §11). **Attribute the Cologne
Digital Sanskrit Dictionaries and `sanskrit-lexicon/MWS`.**

**Known rough edges (future polish, not blocking):** MW glosses retain scholarly abbreviations
(`mfn.`, `RV.`) and occasional pure cross-references (`yoga &c. See pp. 856`); the seed covers the
common words cleanly, so this only shows on rarer lemmas. A cleaner body parser / Apte as a second
dictionary are nice-to-haves.

## Vector store — semantic "essence" retrieval (built)

`vectorstore.py` — **embedded Qdrant** (local file, no Docker) + **fastembed** (ONNX, no PyTorch).
Embeds the English *translation* side of a seed corpus (`corpus.yaml`: famous public-domain verses
with faithful translations), so a sentence's meaning retrieves thematically-related verses:
`search(query)` and `related_passages(parse_result)` (builds the query from the sentence's
dictionary glosses). The store persists to `knowledge/qdrant/` (gitignored); `build_index()` rebuilds.

**Design choices (why):**
- *Embedded Qdrant* — $0, no infra for dev; swap to a Qdrant server at deploy (same API).
- *fastembed over sentence-transformers+PyTorch* — much lighter; Qdrant's native embedder.
- *Embed the English side* — raw-Sanskrit embeddings are weak; we retrieve by meaning through the
  strong English translation (the architecture's caveat).

**Known limit:** BGE-small on 2–3 word gloss-queries is crude. **Upgrades:** BGE-M3 (multilingual,
hybrid dense+sparse) for better recall, and a real verse+commentary corpus (GRETIL texts +
translation datasets) — the bulk-ingestion task parallel to MW above. Then Phase 3's LLM turns
structure + meanings + these retrieved passages into a grounded reading, checked by the verifier.
