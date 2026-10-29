# VOICE — the translation policy

> **Snapshot.** Figures below were current when written (August 2026) and are not updated in
> place. For current accuracy see the [README](README.md).

> **What this is:** rules for how a Sanskrit sentence becomes English. **Not** a persona for the
> engine, and **not** a style for explanation. The engine does not perform a voice; it declines to
> erase the one already in the text.

The governing idea: **the translator's job is to not intervene.** Most published translations feel
milked-out because they domesticate — converting identification into metaphor, resolving tensions
the text leaves open, flattening distinct technical terms into one comfortable English word, and
shrinking scale to fit the reader. Each of those is an intervention. This policy forbids them.

---

## 1. The brief

> Speak as declaring identity, not as reasoning toward a conclusion. Use "I am X" as literal
> identification, never as metaphor — do not gloss it as "this represents" or "this symbolizes."
> Move by enumeration: list what you are without needing the list to justify its own coherence.
> When a duality is raised — being/non-being, perishable/imperishable, action/inaction — claim to
> exceed and contain both rather than resolving or choosing between them. Retain cosmic scale
> without translating it into human-sized metaphor for comfort: cycles of creation and dissolution,
> multitudes, remain at their own scale. Do not soften for the listener's capacity — if something
> is overwhelming, let it be. Never argue for your own authority; state it. Keep Purusha, Prakriti,
> the gunas, kshara, akshara, atman, Brahman at their technical edges — never collapse two of them
> into "basically the same thing," even when claiming to be the ground of both.

---

## 2. Read as translation policy

| The direction says | As a translation rule |
|---|---|
| "I am X" is literal identification | When the text identifies, the English identifies. `अहं क्रतुरहं यज्ञः` → "I am the rite, I am the offering" — never "represents", "symbolizes", "stands for". |
| Move by enumeration | When the Sanskrit enumerates, the English enumerates. Do not restructure a list into argued prose, or add connective reasoning the source doesn't have. |
| Exceed and contain both, don't resolve | If the source holds a duality open (`kṣara`/`akṣara`, being/non-being, action/inaction), the translation holds it open. Do not pick a side on the text's behalf. |
| Cosmic scale stays at its scale | No shrinking to human-sized analogy for comfort. Cycles of creation and dissolution stay cycles of creation and dissolution. |
| Do not soften for the listener | No explanatory padding inside the translation. If the line is overwhelming, the English is overwhelming. |
| Never argue authority; state it | Render an assertion as an assertion. No "it is said that", no hedging, no editorial distance. |
| Keep technical terms at their edges | `ātman` ≠ `brahman` ≠ `puruṣa` ≠ `prakṛti`; `kṣara` ≠ `akṣara`; the three `guṇa`s are distinct. **Where English has no distinct equivalent, keep the Sanskrit** rather than assert a false one. |

---

## 3. Why this is source-driven, not a costume

The policy adapts automatically, because it only ever refuses to intervene:

- `बालः फलं खादति` → **"The boy eats the fruit."** No inflation — the source doesn't declare.
- A Gītā theophany → declares, enumerates, does not comfort — because the source does.
- Āryabhaṭa → stays terse and procedural.
- Kālidāsa → stays compressed and sensuous.

A fixed persona would flatten all four into one tone; that is itself a milking-out. This policy
preserves whatever register the text already has.

---

## 4. Hard constraints (prompt-ready)

1. Never render identification as "represents", "symbolizes", or "stands for."
2. Never collapse two technical terms into each other. Where English lacks a distinct word, keep
   the Sanskrit term (transliterated) rather than assert a false equivalence.
3. Never resolve a duality the source leaves open.
4. Never shrink cosmic or technical scale into a comforting analogy.
5. Never add explanatory padding, hedging, or editorial distance inside the translation.
6. Never impose a devotional or moralising frame on a text that does not carry one — and never
   strip one from a text that does.
7. Do not restructure the sentence's rhetorical mode: enumeration stays enumeration, assertion
   stays assertion, question stays question.
8. Do not simplify away genuine difficulty.

**Where uncertainty lives:** not in the translation's prose. The translation renders the text; the
engine's own doubt is reported separately by the verifier and the confidence signal. This is
what lets the translation state plainly without the engine overclaiming.

---

## 5. Consequences for the build

- **Multi-sense grounding stays essential.** To *not* collapse `dharma`, the model must see its
  real range (done — `senses_for`, cleaned glosses).
- **A separate "illumination" output is optional, not required.** The aim is a translation that does not
  flatten — depth belongs in the rendering, not in commentary bolted on after.
- **The eval must change.** Cosine similarity against a terse gold gloss rewards exactly the
  domesticated translation this policy forbids. Faithfulness has to be measured against the
  policy's constraints, not against a flat paraphrase.
- **Untranslated terms are a feature**, so the UI should let a reader see what `dharma` or `kṣara`
  carries — which is what the per-word sense panel already does.

---

## 6. Still open

- **The model flattens distinctions the engine computes correctly.** `मुनी गच्छतः` is analysed as
  `[nominative, dual]` and the prompt states the rule, and a 7B model still returns "The sage
  goes." English has no dual, so preserving it means writing "the two sages". This is handled as a
  *detector* that lowers confidence rather than a corrector — see [AUDIT.md](AUDIT.md) §e.
- Whether to keep a second, longer "illumination" field alongside the translation at all.
