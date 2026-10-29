# sanskrit-engine

A reading companion for Sanskrit. Paste a verse, get back its grammar — which word is the agent,
which the object, which the instrument — computed from Pāṇini's rules rather than learned from
data.

**The premise:** Sanskrit grammar is stated, not inferred. Pāṇini wrote it down in ~4,000 sūtras
around the 5th century BCE, and it is close to formally complete. So the analysis is *computed*:
no model is trained, and the same input always yields the same output. A language model is used
only at the very end, to phrase a finished analysis in English, and it is never allowed to invent
grammar.

---

## What it produces

```
बालः हस्तेन अन्नं खादति        "the boy eats food with his hand"

बालः      bAla    noun    nominative       boy, child; young
हस्तेन    hasta   noun    instrumental     hand
अन्नम्    anna    noun    accusative       food, grain
खादति     KAd     verb    present (laṭ)    to eat, to consume (√khād)

बालः    --kartā-->   खादति      (agent)
हस्तेन  --karaṇa-->  खादति      (instrument)
अन्नम्  --karma-->   खादति      (object)
```

The roles are **kārakas** — Pāṇini's semantic case categories (1.4.23–55), mapped from the
surface case endings by rule, including the voice inversion at 2.3.18 that swaps agent and object
in the passive.

---

## Measured results

Every number is against ground truth neither I nor the engine authored: the
[Digital Corpus of Sanskrit](https://github.com/OliverHellwig/sanskrit) (human-annotated
CoNLL-U), the Bhagavadgītā's own word-by-word padapāṭha, and the University of Hyderabad kāraka
corpus.

Accuracy is reported **per register**, because a single average hides where the engine breaks:

| register | corpus | lemma | case | number |
|---|---|---|---|---|
| sūtra | Nyāyasūtra, Arthaśāstra | 81.2% | **79.0%** | 89.7% |
| śāstra | Caraka, Sūryasiddhānta, Nāṭyaśāstra | 79.1% | **77.7%** | 90.2% |
| upaniṣad | Kena, Kauṣītaki | 75.0% | **68.1%** | 89.8% |
| kāvya | Meghadūta, Kumārasaṃbhava, Kirātārjunīya | 74.8% | **69.3%** | 89.7% |
| vedic | Ṛgveda, Atharvaveda | 70.4% | **61.5%** | 80.9% |

That 17.4-point spread between sūtra prose and Vedic hymn is the single most useful thing the
evaluation tells me. The engine was originally tuned on classical śāstra prose and reported 73.9%
case accuracy; running the Kena Upaniṣad put it at 58.7%. Nothing had regressed — a second
register had simply never been measured, and a heuristic fitted to one corpus was being reported
as a property of the language.

**Word meaning is far weaker than grammar**, and worth stating plainly:

```
sense accuracy (top-1)   38.7%        the gloss shown first is the right one
sense accuracy (top-3)   45.9%
reachable                60.3%        the correct gloss is somewhere in our data
```

So the grammar layer runs at 61–79% and the meaning layer at 39%. A perfectly parsed sentence
with the wrong glosses is still not understood, and that gap is the honest state of the project.

`209 tests · 20/20 gold sentences pass every stage · 635,112 senses over 214,637 lemmas`

---

## How it works

```
Devanagari / IAST / 14 other scripts & romanisations
        │
   ① normalize      → SLP1 (ASCII). Scheme auto-detected; daṇḍa and Vedic
        │             anunāsika handled; 7 romanisations and
        │             9 Indic scripts accepted.
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
   ⑥ kāraka graph   → case endings become semantic roles, under the voice
                      of each word's own governing verb.
```

Steps ①–④ decide what each word **is**; ⑤ decides what it **means**; ⑥ decides how the words
**relate**. Only step ⑤ touches a language model, and only as one source ranked among six.

### Built on

[**vidyut**](https://github.com/ambuda-org/vidyut) (Rust/Python) for the morphological kosha,
sandhi splitter, Pāṇinian derivation engine and metre identification · the
[**Cologne Digital Sanskrit Dictionaries**](https://www.sanskrit-lexicon.uni-koeln.de/) for
Monier-Williams, Apte and Macdonell · **Pāṇini's Dhātupāṭha** for the 2,229 verbal roots and
their stated meanings.

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "import vidyut; vidyut.download_data('vidyut-data')"   # one-time, ~77 MB
python -m knowledge.dictionary                                    # seed lexicon
python -m knowledge.ingest_mw                                     # Monier-Williams (~44 MB)
```

```bash
streamlit run playground.py     # interactive: stage-by-stage view of any sentence
python -m pytest tests/ -q      # 209 tests
python -m evals.genres          # per-register accuracy table
```

The lexicon, corpora and vidyut data are all **generated or downloaded**, never committed —
every ingest is reproducible from source, records a sha256 of what it read, and quarantines
rejected rows with a reason code instead of dropping them silently.

---

## What doesn't work yet

Kept here deliberately. A portfolio piece that only lists wins is not an engineering document.

- **Vedic is the floor at 61.5% case.** Vedic verb morphology is largely out of reach: its forms
  differ by stem formation rather than suffix, and the subjunctive and injunctive have no
  classical equivalent to map onto.
- **`accusative → nominative` is the dominant error in every register.** An oracle given the true
  object count scores +6.7 to +10.5 points, so the headroom is real. Deciding how many objects a
  clause has needs the verb's valency, and Pāṇini states the category (sakarmaka / akarmaka) while
  no machine-readable source I have carries it. A prior learned from annotation captures about a
  tenth of the available gain.
- **Sense ranking.** The correct gloss is already in the data 60.3% of the time and shown first
  38.7% of the time. Seven strategies have been measured against that gap — cross-dictionary
  consensus, gender agreement, Lesk context overlap, four source orderings — and **none beat
  plain source-authority order.** The refutations are recorded in the code so they are not retried
  blind.
- **One meaning benchmark, one genre.** Sense accuracy is measured only against the Gītā, which
  every language model has likely seen in training, so the LLM-sense contribution should be read
  as an upper bound until a second gloss corpus exists.

### A note on method

Roughly a dozen times, a bad number turned out to be a measurement artifact rather than an engine
defect — a convention difference, a metric that rewarded verbosity, an eval reading a code path
that never shipped. Each would have led to "fixing" something already correct. The habit that
caught them was reading the individual failures before trusting the aggregate, and the evals carry
those corrections in their comments.

---

## Layout

```
core/        the deterministic pipeline — normalize, segment, morphology,
             disambiguate, kāraka graph, metre, compounds
knowledge/   lexicon ingests, dictionary lookup, data-quality plumbing
evals/       measurement harnesses (per-genre, morphology, sense, kāraka)
agents/      the LLM layer: grounded explanation + a verifier that rejects
             any claim not present in the computed analysis
gold/        hand-checked sentences that must pass every stage
tests/       209 unit and fixture tests
```

Each directory has its own README with the design reasoning.

### Design notes

| | |
|---|---|
| [AUDIT.md](AUDIT.md) | six defects found by reading the code against Pāṇini rather than against a benchmark — two of them were changing what sentences mean |
| [COVERAGE.md](COVERAGE.md) | which sūtras are implemented, which are not, and what published work exists that this ignores |
| [STRUCTURAL-DISAMBIGUATION.md](STRUCTURAL-DISAMBIGUATION.md) | a design proposed, measured, and **rejected** — the reasoning kept unedited, because only measurement could have shown it does not pay |
| [VOICE.md](VOICE.md) | the translation policy: what the English is forbidden from doing to the Sanskrit |
| [SPEC.md](SPEC.md) | the original Phase-0 spike spec |

These are dated snapshots, not living documents; current accuracy is the table above.

---

## License

Code: [AGPL-3.0](LICENSE). The curated lexicon and gold set are human work, released CC-BY-SA.
Monier-Williams, Apte and Macdonell are public domain, from the Cologne digitisations; the DCS
and UoHyd corpora remain under their own licenses.
