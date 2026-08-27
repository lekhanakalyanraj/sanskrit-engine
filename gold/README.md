# Gold set

Hand-verified expected output of the deterministic core — the backbone for **golden tests**
(structure), **LLM evals** (meaning), and **regression** snapshots.

Licensed **CC-BY-SA-4.0**: an open community asset that stays open (see PRD §11).

## What's asserted (and what isn't)

Tests assert only what the bundled `sanskrit_parser` lexicon gets **reliably** right:
**segmentation, lemma, part-of-speech, case, and kāraka role.**

Gender is deliberately **not** asserted — the bundled lexicon mislabels it (e.g. it tags neuter
`phala`/`anna` as masculine). That's a known lexicon gap, fixed when the morphology engine is
upgraded to **Vidyut** (Phase 1 evaluation). Asserting it now would bake a wrong value into the
gold data.

## Files

- `everyday.yaml` — simple everyday sentences (the original baseline).
- `coverage.yaml` — sentences that FAILED under the old `sanskrit_parser` stack and now parse
  (proper nouns like राम, `muni`, `paśyati`) — regression protection for the Vidyut migration.
- `domains.yaml` — **mathematics · philosophy · poetry · medicine**. Grammatically simple but
  domain-specific vocabulary (`śūnya`=zero, `ātman`=self, `kāvya`=poetry, `auṣadha`=medicine),
  encoding the product principle that Sanskrit expresses far more than religion (PRD §5) as a
  CI-enforced test. Real classical *verse* is more complex than the current core handles — these
  stay simple on purpose; the point is domain breadth of vocabulary, not syntactic difficulty.

The `domain:` field tags each entry so coverage across domains is queryable.

## Adding entries

Run a candidate through the engine (`inspect.py`, or the playground) and, if the output is
linguistically correct, capture it here. Only add sentences the engine gets **right** — the gold
set is ground truth, not a wishlist.
