# Coverage — grammar, technologies, resources

> **Snapshot.** Figures below were current when written (August 2026) and are not updated in
> place. For current accuracy see the [README](README.md).

An honest audit of what this engine uses, what it does not, and what exists that we have ignored.
Written because the engine was being improved sentence by sentence while substantial published work
sat unexamined.

---

## 1. Pāṇinian coverage

### Implemented

| Area | Sūtras | State |
|---|---|---|
| Sandhi (external) | 6.1.x, 8.2–8.4 | via Vidyut's rule table; joining is deterministic, splitting ambiguous |
| Vibhakti → kāraka | 1.4.23–55, 2.3.x | **voice-aware** — kartari vs karmaṇi assign cases differently (2.3.18) |
| Śeṣe ṣaṣṭhī | 2.3.50 | genitive emitted as `sambandha`, headed by a nominal not the verb |
| Kāraka belongs to its verb | 1.4.23 | each argument attaches to its own clause's verb |
| Avyaya | 1.1.37–38, 5.4.44 ff. | read from the lexicon + taddhita derivation + the nipāta list |
| Kṛdanta as nominals | 3.1–3.4 (partial) | participles take case endings and are treated as nominals, correctly |
| Kartā–verb agreement | — | number agreement constrains subject selection |
| Chandas | — | 145 fixed vṛttas via Vidyut; **anuṣṭubh computed here**, since it has no fixed pattern |

### Not implemented

| Area | Sūtras | Why it matters |
|---|---|---|
| **Samāsa (compounds)** | **2.1–2.2** | **22% of all tokens are compound members and we never decompose.** A tatpuruṣa and a bahuvrīhi of the same members mean different things (`rājaputra` = "king's son" *or* "one whose son is a king"). We look the whole compound up in MW and take whatever it lists — `dharmakṣetre` comes back as "a man of piety and virtue" instead of "in the field of dharma". **This is the largest grammatical gap.** |
| Taddhita | 4.1–5.4 | secondary derivatives are opaque lemmas |
| Karmapravacanīya | 1.4.83–98 | `prati`, `anu` etc. govern a case themselves, so an accusative beside them is not the verb's karma |
| Vākya / anvaya | — | no sentence-level structure; this is what Phase A concluded we would need |
| Vedic accent | — | udātta/anudātta not handled; the recitation guide says so rather than guessing |

---

## 2. Technologies

### In use

**Vidyut** (`ambuda-org/vidyut`) — `kosha` (morphology), `sandhi` (rule table), `lipi`
(transliteration), `chandas` (metre). **Ollama** — local LLM for translation, and a vision model for
image input. **Qdrant + fastembed** — installed for retrieval, currently idle.

### Available and unused

| | |
|---|---|
| **`vidyut.prakriya`** | The actual Pāṇinian **derivation engine** — generates forms *from the sūtras*. Installed, never called. Could validate an analysis by deriving it. |
| **Dhātupāṭha** | **2,229 roots** with Pāṇini's own artha (`BU` → *sattāyām*) and gaṇa. We touch it in exactly one line — as a boolean, to detect kṛdantas — and never read a root's meaning or class. For verbs this is more authoritative than MW. |
| **Sanskrit Heritage Engine** (Huet, INRIA) | The most respected rule-based Sanskrit segmenter and morphological analyser. |
| **Kulkarni's kāraka parser** (Univ. of Hyderabad) | Constraint-based Pāṇinian parsing — the structural layer Phase A said the 22–26 pt gaps require. |

### Deliberately excluded

No training or fine-tuning; no cloud APIs; no full dependency parser (Phase A measured the pairwise
shortcut and it did not convert). **These were choices, not oversights — but they should be
re-examined now that a measurement harness exists to test whether a given tool actually helps.** The
neural Chedaka was removed because it *measurably hurt*, not on principle.

---

## 3. Resources

### In use

**Monier-Williams** (~248k senses after cleaning) · **DCS** — 6 texts of 271 · **Vidyut data**.

### Available and unused

**Dictionaries — we use 1 of 25**, all at a URL we already download from
(`tokushige-koyasan/cdsl-corpus`):

| file | dictionary | why it matters |
|---|---|---|
| `ap90.tsv` | **Apte, Practical Sanskrit-English** | written for *reading texts* — short glosses, no citation apparatus. Most of what we spent days stripping out of MW is simply not in Apte. |
| `md.tsv` | **Macdonell, student's dictionary** | concise, same reason |
| `shs`, `cae`, `mw72`, `mwe`, `pw`, `pwg`, `gra`, … | 22 more | Böhtlingk-Roth, Cappeller, Grassmann (Ṛgveda-specific) |

**Corpora and tooling:**

| | |
|---|---|
| `OliverHellwig/sanskrit` | DCS — **265 more texts** than we ingest |
| `gita/gita` | the Bhagavad Gītā in JSON — **one of our actual target texts**, structured and ready |
| `Ashutosh-Vijay/Valmiki_Ramayan_Dataset` | Rāmāyaṇa, structured |
| `rahular/itihasa` | large Sanskrit–English parallel corpus |
| `Jivnesh/SanskritShala` | neural toolkit: segmentation, morphological tagging, **dependency parsing, compound identification** |
| `dharmamitra/byt5-sanskrit-analyzers` | ByT5-Sanskrit — segmentation, lemmatisation, morphosyntax |
| `cvikasreddy/skt` | **compound segmentation** specifically — aimed at our largest gap |
| `sanskrit/sanskrit`, `sanskrit/data` | general-purpose library and versioned linguistic data |
| `sanskrit-coders/chandas` | more metre data than Vidyut's 145 |
| Sanskrit WordNet | sense inventory — would make sense-selection measurable, which it currently is not (DCS carries sense IDs on only 2.1% of tokens) |

---

## 4. What this audit changes

1. **Apte before anything else.** One line of config, a real lexicon, zero hallucination risk, and it
   addresses the gloss-quality problem directly — which is what a reader hit on day one.
2. **Read the Dhātupāṭha.** 2,229 authoritative root meanings, already on disk, used as a boolean.
3. **Compounds are the real grammatical gap** — 22% of tokens, and existing work targets it.
4. **Re-test the neural tools.** The harness can now measure whether SanskritShala or ByT5 beat our
   65% segmentation. Chedaka was dropped because it measured worse; that is the standard to apply,
   not a blanket rule against models.
5. **Use the target texts.** The Gītā is available as structured JSON. Every accuracy number in this
   project is measured on prose that is not what the user wants to read.
