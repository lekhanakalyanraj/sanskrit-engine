# Audit — reading the code against the grammar

> **Snapshot.** Figures below were current when written (August 2026) and are not updated in
> place. For current accuracy see the [README](README.md).

Six defects found by checking the implementation against Pāṇini rather than against a benchmark.
Two of them were changing what sentences *mean*. None was found by measuring.

This is kept as a worked record because it is the clearest evidence of how the project is built:
where a specification exists, it is something to implement, not something to tune toward.

---


For stretches of this project the instrument was wrong. Sanskrit's rules are *written down*, and
the engine's job is to compute them — so the way to find a defect is often to read the
implementation against the sūtra, not to tune against a score. Auditing `core/karaka.py` against
Pāṇini found defects no amount of measurement would have named, because they were not close calls.
They were the grammar being contradicted.

### a. Voice was never read — and it inverts meaning

The kosha carries `prayoga` (kartari / karmaṇi) and we ignored it. Pāṇini assigns the cases by
voice:

| | kartā | karma |
|---|---|---|
| kartari (active) | prathamā (nom.) | dvitīyā (acc.) |
| karmaṇi (passive) | **tṛtīyā (instr.)** — 2.3.18 | **prathamā (nom.)** |

`CASE_TO_KARAKA` hardcoded the active row, so **11.5% of verbed sentences** came out with agent and
object exchanged. `रामेण ओदनः पच्यते` read as *"the rice cooks by means of Rāma."* Not a wrong
label — the reversal of who does what to whom, delivered at high confidence, in the layer that is
supposed to be this project's differentiator.

### b. A kāraka belongs to ITS verb (1.4.23)

`build_karaka_edges` took `next(...)` — the first finite verb — and attached every nominal to it.
In the 4.0% of sentences where the engine now finds several verbs, clause two's arguments were
being handed to clause one's verb. Resolved verb-finally (a nominal's verb is the next one to its
right), with the agreement constraint breaking ties for the kartā.

### c. The genitive got no edge at all (2.3.50 śeṣe ṣaṣṭhī)

The sixth case covers the *remainder* — relations that are not kārakas — so its head is another
nominal, never the verb. 5.4% of tokens are genitive and the graph showed the reader nothing for
them. Now emitted as `sambandha`.

### First external validation of the kāraka layer

Against DCS's own dependency annotations (the Vedic Treebank subset, 89 annotated tokens — small,
but ground truth we did not author):

| | |
|---|---|
| correct role | 46/89 = **51.7%** |
| …excluding a convention difference (below) | 46/71 = **64.8%** |
| **sambandha** | **13/13** |

The convention difference is one of several this project has hit: 18 of the missing edges are in
sentences DCS itself marks **verbless**. With no kriyā there is no kāraka, so Pāṇini assigns none;
UD labels a subject anyway because its formalism needs a head for every token. The remaining real
errors are dominated by `karma` read as `kartā` (12), which is the known case-selection gap.

### The lesson

Four exchanges went into heuristics that returned −13.3, +0.8, 0.0, −0.3 and a revert, while the
layer above them contradicted the grammar on every passive sentence. **A specification is not
something to tune against; it is something to implement.** The measurement layer earns its place
catching what the specification does not cover — conventions, ambiguity, ranking among readings the
grammar leaves genuinely open — and not as a substitute for reading the rules.

### d. Avyaya was hand-listed instead of read (1.1.37, 1.1.38, 5.4.44 ff.)

`PARTICLES` covered ~30 words by hand, with a docstring calling the class "a fact about Sanskrit
rather than a heuristic" — and then implementing it by hand anyway. Vidyut flags avyayas across the
whole lexicon, and **541 tokens** DCS calls indeclinable were missing from our list. Every one was
inflected, given a case, and entered the kāraka graph as a spurious argument: the `na` → `nā`
("navel") bug, never actually finished.

Three grammatical routes now, in place of the hand list:

| | |
|---|---|
| lexicon flags avyaya **and** offers no nominal reading | unambiguous |
| taddhita adverbs by derivation — `-tas`, `-tra`, `-dā`, `-thā` (1.1.38) | outranks a spurious nominal entry |
| the nipāta / svarādi list (1.1.37) | a closed class, so transcribing it *is* the grammar |

Spurious kāraka arguments from indeclinables: **518 → 301**. Lemma accuracy +1.0 pt. The avyaya
flag turns out to separate `atra`/`tatra`/`yatra` (True) from `patra`/`mitra`/`netra`/`gotra`
(False) on its own, so the `-tra` rule needs no length guard.

### e. The grammar never reached the translator

`build_grounding` passed the LLM a lemma, a kāraka role and the dictionary senses — and **no tense,
mood, voice, person or number**. `gacchati` ("he goes") and `gacchatu` ("let him go") arrived
identically. Having just computed voice, we were not telling anyone.

Fixed, and the effect is measurable end to end:

| | before | after |
|---|---|---|
| `रामेण ओदनः पच्यते` | "Rāma cooks the porridge." | **"The rice is cooked by Rama."** |

The dual did **not** follow. `मुनी गच्छतः` is analysed correctly as `[nominative, dual]`, the prompt
states the rule explicitly, and qwen2.5:7b still returns "The sage goes." The structural layer is
right and the model flattens it anyway.

That is precisely the split the two-tier trust model exists for, so it is handled where it belongs
— in the policy layer, mechanically:

* **passive stays passive** — a karmaṇi verb whose English reads active is flagged
* **a dual is not a plural** — English has no dual form, so preserving the distinction means saying
  "the two X"; a translation that does not is flagged

Both are detectors that lower confidence, never correctors. A structural layer that is right and a
model that is fallible is a solvable arrangement; the reverse is not.

### f. Upasarga survived the engine and died in the dictionary

A prefix changes both the sense and the government of a root — `gam` "go", `adhigam` "attain",
`saṃgam` "meet", `udgam` "rise". The morphology layer was already correct: it keeps the prefix in
the lemma (`aDigam`, not `gam`).

The dictionary then had nothing to say. `Agam`, `saMgam`, `udgam`, `anugam` returned **zero senses**,
so `āgacchati` ("comes") showed the reader no meaning at all *and* tripped the "no dictionary
meaning" signal that lowers the engine's own confidence.

The cause was ours, not MW's — MW carries all of them. `clean_gloss` rejected an entry outright
whenever `_CONJ` matched anywhere in it:

    _CONJ = re.compile(r"Dhātup\.|\bcl\.\s*\d+\.?\s*[PĀ]\.|…")

That filter exists to drop entries whose "sense" is a conjugation table. But nearly every verb entry
*states* its conjugation before defining the root, so the filter discarded **1,576 entries, 1,260 of
them containing real definitions** — concentrated in verb roots, which anchor the whole kāraka graph.

Fixed by salvaging rather than lifting the filter: MW glosses a root with an English infinitive, so
the first `to <verb>` is a reliable boundary between apparatus and meaning. Where no infinitive
follows, the entry really is a bare paradigm and is still rejected.

**+2,518 senses, +1,997 lemmas**, and purely additive — those entries previously produced no row, so
nothing existing moved, and seed senses still rank first. Verified on fixtures *before* re-ingesting,
which is the lesson from the earlier incident where an over-eager stripper gutted 2,187 entries.

### The shape of the whole audit

| | found by |
|---|---|
| voice inverting kartā and karma on 11.5% of verbed sentences | reading 2.3.18 |
| kārakas attached to the wrong verb (1.4.23) | reading the code |
| genitive emitting no edge at all (2.3.50) | reading the code |
| 541 indeclinables inflected into the graph (1.1.37–38) | reading the lexicon's own flag |
| tense, mood, voice and number withheld from the translator | reading `build_grounding` |
| 1,260 verb definitions discarded by our own filter | following the prefix through the stack |

Not one of these was found by measuring. Every one was found by reading the implementation against
the specification — and two of them were changing what sentences *mean*.
