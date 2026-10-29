LLM SENSE GENERATION — run on your own machine
==============================================

Produces one short English gloss per Sanskrit lemma, from the model's own knowledge.
Nothing here needs the Sanskrit engine: stdlib Python + Ollama only.

WHAT YOU NEED
  1. Python 3.9+            python --version
  2. Ollama                 https://ollama.com/download
  3. The model              ollama pull qwen2.5:7b

RUN IT
  cd llm-sense-bundle
  python generate_senses.py --limit 200        # smoke test, ~1 minute
  python generate_senses.py --workers 8        # the full run

  Resumable. Ctrl-C any time; re-run and it continues from llm_sense.json.
  Progress saves every 200 words and prints an ETA.

YOUR HARDWARE (RTX 5070 12GB / 64GB RAM / Core Ultra 5)
  qwen2.5:7b uses ~5GB VRAM at Q4 — fits with room to spare.
  Start with --workers 8. If VRAM tops out, drop to 4.
  Expect roughly 3-8 hours for the full list; the macOS pilot ran 3.6/s single-threaded.

  Optional: `ollama pull qwen2.5:14b` also fits in 12GB at Q4 and should gloss better.
  Generate with 7b FIRST so the result is comparable to the measured pilot, then try 14b
  into a separate file and we can measure whether it is actually better:
      python generate_senses.py --model qwen2.5:14b

WHEN IT FINISHES
  Send back  llm_sense.json  (that file is the entire deliverable).

WHAT IT DOES NOT DO
  It never sees a dictionary entry or a verse — only the bare stem. That is deliberate:
  it keeps the output an independent source rather than a rewrite of what we already hold.
