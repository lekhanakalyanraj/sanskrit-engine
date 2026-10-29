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

### Corpus — curated seed + bulk ingestion (done)

`ingest_corpus.py` pulls all **700 Bhagavad Gītā verses** from
[AdiyogiArts/gita-json](https://github.com/AdiyogiArts/gita-json) (**MIT**) — Devanagari, IAST,
English translation, and a per-verse **commentary**. Normalised to `corpus_gita.json` (gitignored,
regenerable), loaded by `build_index()` alongside the curated `corpus.yaml` seed.

```bash
python -m knowledge.ingest_corpus     # download + normalise (701 verses)
python -m knowledge.vectorstore       # rebuild the index (~95s for 709 passages)
```

**We embed translation + commentary**, not translation alone: a verse's essence lives in how it is
expounded, so commentary makes thematic matching far sharper. Measured effect — the query *"do your
work without attachment"* went from returning a generic subhāṣita to returning **BG 3.19, 4.14 and
2.47**, the karma-yoga verses.

Feeding those passages to the explainer did **not** contaminate translations (mean similarity
0.989, grounded 10/10) — the prompt marks them as context, and the verifier is the backstop.

**Known limit:** BGE-small is still English-only and crude on 2–3 word gloss queries.
**Next upgrade:** BGE-M3 (multilingual, hybrid dense+sparse), and more texts beyond the Gītā
(Upaniṣads, kāvya, śāstra) so the corpus matches the project's non-religious breadth.
