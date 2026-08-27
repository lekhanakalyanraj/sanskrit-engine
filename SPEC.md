# Phase-0 Spike Spec — Sanskrit Understanding Engine

**Goal of Phase 0:** prove the *deterministic core* wires together end to end on **one
hardcoded sentence** — no training data, no product UI, no scale. Just:

```
Devanagari input → SLP1 → segmentation → morphology → kāraka graph → meaning
```

If a single sentence flows cleanly through all five stages and produces a correct
kāraka graph with dictionary meanings, the architecture is validated and Phase 1
(interactive app, more sentences) is de-risked.

---

## Success criteria (all must pass)

1. **Stage 0** — Devanagari input is transliterated to SLP1 and back losslessly.
2. **Stage 1** — a sentence *with sandhi* is split back into its component words
   (proves segmentation does real work, not whitespace tokenization).
3. **Stage 2** — each word gets a morphological analysis: lemma + case/number/gender
   (nouns) or root/tense/person (verbs).
4. **Stage 3** — each lemma resolves to at least one Monier-Williams dictionary sense.
5. **Stage 4** — a kāraka graph is produced: nodes = words, edges = semantic roles
   (kartā / karma / karaṇa …), rendered to `graph.json`.
6. The whole thing runs from `python spike.py` and prints a readable report.

**Non-goals for Phase 0:** disambiguation quality, multiple sentences, web UI,
handling every input script, evaluation harness. Those are Phase 1+.

---

## Test sentences

**Primary (get this green first)** — clean, whitespace-separated, canonical first sentence:

> रामः वनं गच्छति — *rāmaḥ vanaṃ gacchati* — "Rama goes to the forest."
>
> Expected kāraka graph: `rāma —kartā→ gacchati`, `vana —karma→ gacchati`.

**Target (graduate to this — it proves sandhi splitting + a 3-role graph)**:

> बालो हस्तेनान्नं खादति — *bālo hastenānnaṃ khādati* — "The boy eats food with his hand."
>
> Sandhi to undo: `bālaḥ→bālo` (visarga), `hastena+annaṃ→hastenānnaṃ` (vowel).
> Expected graph: `bāla —kartā→ khādati`, `hasta —karaṇa→ khādati`, `anna —karma→ khādati`.
> Three roles = the "who does what to whom by what means" essence, made visible.

---

## The five stages — exact tooling

| Stage | Library (pip) | Deterministic? |
|---|---|---|
| 0. Transliterate | `indic-transliteration` | ✅ fully |
| 1. Segment (sandhi split) | `sanskrit_parser` | ⚠️ candidates, ambiguous |
| 2. Morphology | `sanskrit_parser` | ⚠️ multi-valued |
| 3. Lexicon lookup | `pycdsl` (Monier-Williams) | ✅ lookup |
| 4. Kāraka graph | `sanskrit_parser` relations + deterministic case→role fallback | 🟡 rule-driven |

`sanskrit_parser` is the workhorse for Phase 0: it does segmentation, morphology,
**and** a dependency parse in one library — the fastest path to a green end-to-end run.
(Vidyut / Saṃsādhanī come in Phase 1 when we harden each stage.)

### Deterministic kāraka fallback (always works)

If `sanskrit_parser`'s dependency edges are noisy, fall back to a pure rule map from
**vibhakti (case) → kāraka role**, so the hero graph always renders:

| Case (vibhakti) | Default kāraka role |
|---|---|
| Nominative (prathamā) | kartā (agent) |
| Accusative (dvitīyā) | karma (object) |
| Instrumental (tṛtīyā) | karaṇa (instrument) |
| Dative (caturthī) | sampradāna (recipient) |
| Ablative (pañcamī) | apādāna (source) |
| Locative (saptamī) | adhikaraṇa (locus) |

This is a *simplification* (case doesn't map 1:1 to role in the general case — that's
exactly the ambiguity Phase 1's disambiguator handles) but it's correct for the
Phase-0 test sentences and guarantees a visible graph.

---

## Data model (see `models.py`)

One growing structure — a lattice that gets annotated stage by stage:

- **Token** — surface word + char span in the original
- **Analysis** — `{lemma, pos, features}` (case/number/gender or root/tense/person)
- **Sense** — dictionary entry (source + gloss)
- **KarakaEdge** — `{head, dependent, role}`
- **ParseResult** — the whole thing, serializable to `graph.json`

`graph.json` shape (what a future frontend renders):

```json
{
  "sentence_devanagari": "...",
  "nodes": [{"id": 0, "surface": "रामः", "lemma": "राम", "pos": "noun",
             "features": {"case": "nominative", "number": "singular"},
             "senses": ["Rama, a proper name"]}],
  "edges": [{"head": 2, "dependent": 0, "role": "kartā"}]
}
```

---

## Build checklist

- [ ] `pip install -r requirements.txt`
- [ ] Stage 0 round-trips Devanagari ↔ SLP1
- [ ] Stage 1 splits the primary sentence
- [ ] Stage 2 gives morphology per word (inspect raw `serializable()` output, map to `Analysis`)
- [ ] Stage 3 returns a Monier-Williams gloss for each lemma (first run downloads MW)
- [ ] Stage 4 emits `graph.json` with kartā/karma edges
- [ ] Graduate to the target sentence (sandhi split + 3-role graph)
- [ ] (optional) render `graph.json` to a PNG via graphviz

## Phase-0 findings (from the actual build)

These surfaced by running the spike — exactly what Phase 0 is for:

1. **Don't use `sanskrit_parser`'s sentence/vakya parser (`split.parse()`).** On the
   canonical sentence it returned *no correct parse in 10 candidates* (read रामः as a
   verb, गच्छति as a participle) and emitted `score=None`. Its disambiguation is unusable here.
2. **Go one level lower — per-word morphology via `LexicalLookupFactory.create("combined")`
   → `get_tags(word)` — which IS correct.** गच्छति's top analysis there is the right
   finite verb (गम्, laṭ, 3sg). This is more faithful to the deterministic-core thesis anyway.
3. **Feed the lexicon the segmenter's `-as`/`-am` form, not the visarga `-aḥ` form.**
   `bAlaH` → 0 analyses, but `bAlas` → nominative singular masculine. ✓
4. **The bundled lexicon lacks proper nouns** (राम = 0 analyses). Use common nouns for
   Phase-0 demos; treat proper-noun coverage as a Phase-1 data task.
5. **Segmentation needs deterministic candidate selection.** The parser's #1 split
   over-segments (हस्तेन→हस्ते+न). Rule that works: among candidates, prefer all-segments-valid,
   then fewest segments (longest-word preference). The correct split then wins.
6. **Kāraka derives cleanly from vibhakti** (nominative→kartā, instrumental→karaṇa,
   accusative→karma) once morphology is right. The graph is sound by construction.
7. **Phase-1 engine decision:** evaluate **Vidyut** / **Heritage** / **Saṃsādhanī** to
   replace both the lexicon (coverage) and add proper disambiguation. `sanskrit_parser`
   got us to a green spike; it is not the production morphology/parse layer.

## Known Phase-0 risks

- **`sanskrit_parser` API drift** — verify `.split()` / `.parse()` / `.serializable()`
  signatures against the installed version; the spike prints raw output so you can
  adapt the mapper.
- **First `pycdsl` run downloads Monier-Williams** (~tens of MB) — needs network once.
- **Kāraka edges from the parser may use its own relation names** — that's why the
  deterministic case→role fallback exists.
