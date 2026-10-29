# sanskrit-engine

A reading companion for Sanskrit. Paste a verse, get back its grammar — which word is the agent,
which the object, which the instrument — computed from Pāṇini's rules rather than learned from
data.

Sanskrit grammar is stated, not inferred: Pāṇini wrote it down in ~4,000 sūtras around the 5th
century BCE, and it is close to formally complete. So the analysis is *computed* — no model is
trained, and the same input always yields the same output. A language model is used only at the
end, to phrase a finished analysis in English, and never to supply grammar.

---

## What it produces

```
बालः हस्तेन अन्नं खादति        "the boy eats food with his hand"

बालः      bAla    noun    nominative       boy, child; young
हस्तेन    hasta   noun    instrumental     hand
अन्नम्    anna    noun    accusative       food, grain
खादति     KAd     verb    present (laṭ)    to eat, to consume (√khād)

बालः    --kartā-->   खादति      the one who acts
हस्तेन  --karaṇa-->  खादति      the means
अन्नम्  --karma-->   खादति      the one acted on
```

The roles are **kārakas** — Pāṇini's semantic participant roles (1.4.23–55), mapped from the
surface case endings by rule.

They are roles, not syntactic functions, and the difference is the reason this layer exists.
`karma` is *what the action reaches* (1.4.49 `kartur īpsitatamaṃ karma`), which is not the same as
"direct object":

```
बालः अन्नं खादति       annam — accusative, grammatical object,  karma
अन्नं बालेन खाद्यते    annam — nominative, grammatical SUBJECT, still karma
```

Same participant, same role, different case. A parser that records "subject" and "object" loses
that; one that records kārakas does not. Handling it requires reading the verb's voice, which is
what 2.3.18 (`kartṛkaraṇayos tṛtīyā`) specifies and what `CASE_TO_KARAKA_PASSIVE` implements.

---

## Accuracy

Measured against external ground truth: the
[Digital Corpus of Sanskrit](https://github.com/OliverHellwig/sanskrit) (human-annotated CoNLL-U),
the Bhagavadgītā's word-by-word padapāṭha, and the University of Hyderabad kāraka corpus.

Reported per register, since a single average hides a 17.4-point spread:

| register | corpus | lemma | case | number |
|---|---|---|---|---|
| sūtra | Nyāyasūtra, Arthaśāstra | 81.2% | **79.0%** | 89.7% |
| śāstra | Caraka, Sūryasiddhānta, Nāṭyaśāstra | 79.1% | **77.7%** | 90.2% |
| upaniṣad | Kena, Kauṣītaki | 75.0% | **68.1%** | 89.8% |
| kāvya | Meghadūta, Kumārasaṃbhava, Kirātārjunīya | 74.8% | **69.3%** | 89.7% |
| vedic | Ṛgveda, Atharvaveda | 70.4% | **61.5%** | 80.9% |

The engine was tuned on classical śāstra prose and reported 73.9% case accuracy on it. Adding the
Kena Upaniṣad put that register at 58.7% — nothing had regressed, but a rule fitted to one corpus
had been reported as a property of the language. `evals/genres.py` now scores each register
separately so a change cannot improve the mean while destroying a register.

Word sense is weaker than grammar:

```
sense top-1    38.7%     the gloss shown first is the right one
sense top-3    45.9%
reachable      60.3%     the correct gloss is somewhere in the data
```

Grammar runs at 61–79%, sense at 39%. A correctly parsed sentence with the wrong glosses is still
not readable, so sense is the binding constraint.

`209 tests · 20/20 gold sentences pass every stage · 635,112 senses over 214,637 lemmas`

---

## How it works

```
Devanagari / IAST / 14 other scripts & romanisations
        │
   ① normalize      → SLP1 (ASCII). Scheme auto-detected; 7 romanisations and
        │             9 Indic scripts accepted; daṇḍa and Vedic anunāsika handled.
   ② segment        → undo sandhi, split into padas.
        │
   ③ morphology     → every grammatically possible reading of each pada.
        │
   ④ disambiguate   → choose one, using verb agreement (3.4.69), number
        │             markedness (1.4.22), and a learned verb-valency prior.
        │
   ⑤ dictionary     → gloss the LEMMA. Curated > Dhātupāṭha > LLM > Apte >
        │             Macdonell > Monier-Williams.
        │
   ⑥ kāraka graph   → case endings become semantic roles, under the voice of
                      each word's own governing verb.
```

Steps ①–④ decide what each word **is**, ⑤ what it **means**, ⑥ how the words **relate**. Only ⑤
touches a language model, as one source ranked among six.

**Built on** [vidyut](https://github.com/ambuda-org/vidyut) (Rust/Python) for the morphological
kosha, sandhi splitter, Pāṇinian derivation engine and metre identification · the
[Cologne Digital Sanskrit Dictionaries](https://www.sanskrit-lexicon.uni-koeln.de/) for
Monier-Williams, Apte and Macdonell · Pāṇini's Dhātupāṭha for 2,229 verbal roots.

---

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "import vidyut; vidyut.download_data('vidyut-data')"   # one-time, ~77 MB
python -m knowledge.dictionary                                    # seed lexicon
python -m knowledge.ingest_mw                                     # Monier-Williams, ~44 MB
```

Optional extra lexicons and corpora:

```bash
python -m knowledge.ingest_apte          # Apte
python -m knowledge.ingest_macdonell     # Macdonell
python -m knowledge.ingest_dhatupatha    # Dhātupāṭha roots
python -m knowledge.ingest_dcs           # DCS corpus cache (needs `gh`)
python -m knowledge.ingest_valency       # verb-valency prior (needs the DCS cache)
```

Run it:

```bash
streamlit run playground.py     # stage-by-stage view of any sentence
python -m pytest tests/ -q      # 209 tests
python -m evals.genres          # per-register accuracy
python -m evals.sense_ranking   # sense accuracy vs the Gītā padapāṭha
```

The lexicon, corpora and vidyut data are generated or downloaded, never committed. Each ingest
records a sha256 of its source, balances `rows_in == rows_kept + rows_rejected`, and writes
rejected rows to a `sense_rejected` table with a reason code rather than dropping them.

---

## Known limitations

- **Vedic is the floor at 61.5% case.** Vedic verb forms differ from classical by stem formation
  rather than by suffix, so no string mapping reaches them, and the subjunctive and injunctive have
  no classical equivalent. Nominal endings (`-āsaḥ` 7.1.50, `-ebhiḥ` 7.1.9, the anunāsika) are
  handled; verbs are not.
- **`accusative → nominative` is the dominant error in every register.** An oracle given the true
  object count per sentence scores +6.7 to +10.5 points. Resolving it needs verb valency; Pāṇini
  states the category (sakarmaka / akarmaka) but no machine-readable source carries it, and
  `knowledge/ingest_valency.py` recovers roughly a tenth of the available gain from annotation.
- **Sense ranking is unsolved.** The correct gloss is in the data 60.3% of the time and shown first
  38.7% of the time. Seven strategies were measured against that gap — cross-dictionary consensus,
  gender agreement, Lesk context overlap, four source orderings — and none beat plain
  source-authority order. Each refutation is recorded at its call site.
- **Sense is measured on one text.** Only the Gītā has per-word gold glosses, and language models
  have likely seen it in training, so the LLM-sense contribution is an upper bound.
- **OCR is untested on photographs.** `core/ocr.py` has only been run against font renders.

---

## Layout

```
core/        the deterministic pipeline — normalize, segment, morphology,
             disambiguate, kāraka graph, metre, compounds
knowledge/   lexicon ingests, dictionary lookup, data-quality plumbing
evals/       measurement harnesses (per-register, morphology, sense, kāraka)
agents/      the LLM layer: grounded explanation + a verifier that rejects
             any claim absent from the computed analysis
gold/        hand-checked sentences that must pass every stage
tests/       209 unit and fixture tests
```

Each directory has its own README. Design notes:

| | |
|---|---|
| [AUDIT.md](AUDIT.md) | six defects found by reading the code against Pāṇini rather than against a benchmark |
| [COVERAGE.md](COVERAGE.md) | which sūtras are implemented, which are not, and related published work |
| [STRUCTURAL-DISAMBIGUATION.md](STRUCTURAL-DISAMBIGUATION.md) | a design proposed, measured and rejected; the original reasoning kept unedited |
| [VOICE.md](VOICE.md) | translation policy — what the English may not do to the Sanskrit |
| [SPEC.md](SPEC.md) | the original Phase-0 spike spec |

Those are dated snapshots; current accuracy is the table above.

---

## License

Code: [AGPL-3.0](LICENSE). The curated lexicon and gold set are human work, released CC-BY-SA.
Monier-Williams, Apte and Macdonell are public domain via the Cologne digitisations. The DCS and
UoHyd corpora are not redistributed here and remain under their own licenses.
