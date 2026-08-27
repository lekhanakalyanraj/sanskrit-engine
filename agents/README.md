# Agentic layer (Stage 4) — grounded explanation + verifier

The payoff layer: `understand(sentence)` runs the whole engine —
**core (structure) → dictionary (meaning) → vector (essence) → explain → verify** — and returns a
grounded English reading with a confidence signal.

## The narrow-LLM principle

The LLM does **only** two things, both deliberately small:
- **`explainer.py`** — phrase the *already-computed* structure (kāraka roles) + dictionary meanings
  (+ retrieved passages) into fluent English. It does **no grammar** (deterministic) and must
  invent **no facts** (grounded in the supplied words/meanings).
- **`verifier.py`** — check that every claim in the reading is supported by the grounding, and fold
  in **deterministic** core signals (no verb found, unrecognised word, missing meaning) that can
  only *lower* confidence.

This is why the engine can use a small **open** model (Ollama, via `llm.py`) where a pure-LLM
Sanskrit translator would hallucinate: the model isn't doing the hard part. The verifier carries
extra weight precisely because small models follow "cite only what's grounded" less rigidly
(PRD §7, two-tier trust).

Orchestration is **plain Python** — the flow is a fixed pipeline, not autonomous agents.

## Testing without a live model

`explain`/`verify`/`understand` take an injectable `llm` callable. `tests/test_agents.py` passes a
**stub** that returns canned typed objects, so grounding construction, orchestration, and the
confidence logic are tested deterministically — **no Ollama or API key needed for CI.** The *live*
generation runs on a machine with a model reachable (`ollama serve` + `ollama pull qwen2.5:7b`, or
a provider API key). The build environment had neither, so the live path is built and stub-tested
but was not exercised end-to-end here.

## Dev gotcha — embedded Qdrant is single-process

The vector store (`knowledge/qdrant/`) is a local file that **only one process can open at a time.**
So a running `streamlit run playground.py` holds the lock and `pytest` (which touches the vector
store) will fail with *"already accessed by another instance"* — and vice-versa. **Stop the
playground before running the vector/agent tests.** (At deploy, a Qdrant server removes this limit.)

## Next

BGE-M3 + a real verse/commentary corpus make the retrieved "essence" genuinely rich; the explainer
prompt then has real commentary to ground a deeper reading. Tune the explainer/verifier prompts
against your chosen open model, and add a small human-reviewed eval set (RAGAS-style) per PLAN.
