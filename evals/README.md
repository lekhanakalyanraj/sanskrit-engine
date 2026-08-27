# Evals — measuring the LLM layer

The deterministic core is covered by exact golden tests. The *LLM* layer can't be asserted the
same way, so it gets **measurement** (this folder) plus **adversarial tests**
(`tests/test_verifier_redteam.py`). Together they close PLAN.md's Phase-3 exit gate.

## Faithfulness eval

```bash
python -m evals.faithfulness            # whole gold set
python -m evals.faithfulness --limit 5  # quick pass
```

Runs the real explainer + verifier over every gold sentence and scores its translation against the
hand-verified `gloss_en` by **semantic similarity** (cosine over the BGE embeddings we already
ship) — because many translations are equally correct ("the boy eats fruit" / "a boy is eating
fruit"), exact match would be meaningless.

**Read the deltas, not the absolute number.** It's a regression signal for prompt/model/data
changes, not a quality score.

### Baseline — qwen2.5:7b, 20 gold sentences

| run | mean sim | min | grounded |
|---|---|---|---|
| initial | 0.964 | 0.704 | 17/20 |
| after gloss reorder + verifier tuning | **0.984** | **0.919** | **19/20** |

The eval paid for itself immediately: it found that the *seed lexicon's gloss order* drove
translation choice — `gaṇaka: "calculator, mathematician"` made the model render a mathematics
sentence as *"The calculator understands the void"*. Reordering to `"mathematician, calculator"`
(and `śūnya` → `"zero (the mathematical zero); empty, void"`) turned that case from 0.704 → 1.000
(*"The mathematician knows zero."*). **Gloss order is a tuning surface** — noted in
`knowledge/dictionary.yaml`.

## Verifier red-team

```bash
pytest tests/test_verifier_redteam.py   # auto-skips when no LLM is reachable
pytest -m "not llm"                     # skip all live-LLM tests
```

Feeds the verifier deliberately hallucinated readings of a correctly-parsed sentence — invented
location, invented entity, swapped roles, invented detail — and asserts each is flagged, with a
faithful control asserting we don't just reject everything. **This is the project's trust claim,
tested against a real model rather than a stub.**

It also acts as a guard when tuning: loosening the verifier prompt to cut false positives
immediately made it miss *"in the forest"* and *"at dawn"* — the red-team caught the regression
before it shipped, which is exactly why it was built first.

## How the verifier ended up

Two complementary passes, mirroring the project's thesis:

- **LLM pass** — semantic judgement (role reversals, contradictions, meaning).
- **Deterministic pass** (`unsupported_terms`) — pure lexical: every content word in the reading
  must trace to a dictionary gloss, a lemma, or a kāraka role name. A 7B model is unreliable at
  spotting added detail; this isn't. Measured 3/3 legitimate paraphrases accepted, 2/2
  hallucinations flagged.

Signals are graded, not equal: a **hard** signal (no verb, unknown word, no gloss) means the parse
is unsound → not grounded. A **soft** signal (a term that could be added content *or* just a
synonym like "flows" for "to go") warns and caps confidence at medium.
