#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Generate a short plain English gloss for every Sanskrit lemma, using a local Ollama model.

STANDALONE ON PURPOSE. Standard library only — no pip install, no vidyut, no database, no project
code. It reads `lemmas.tsv`, talks to Ollama over HTTP, and writes `llm_sense.json`. That is all,
so it runs on a fresh Windows box with nothing but Python and Ollama installed.

The model is shown the STEM ALONE — never a dictionary entry, never a verse. The point is its own
knowledge of the word, which also keeps the result an independent source rather than a paraphrase
of a dictionary we already have.

Resumable: progress is flushed to llm_sense.json every 200 words, and re-running skips whatever is
already there. Ctrl-C is safe; just run it again.

    python generate_senses.py                  # all of it, 4 workers
    python generate_senses.py --workers 8       # faster on a bigger GPU
    python generate_senses.py --model qwen2.5:14b
    python generate_senses.py --limit 200       # quick smoke test first
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEMMAS = HERE / "lemmas.tsv"
OUT = HERE / "llm_sense.json"

SYSTEM = (
    "You are a Sanskrit lexicographer. Given a Sanskrit word STEM, reply with its core meaning "
    "as 2-5 comma-separated English words or short phrases. No explanation, no grammar labels, "
    "no transliteration, no numbering. If the stem is a verbal root, give the action "
    "(e.g. 'to go, to move'). If you do not know the word, reply exactly: UNKNOWN"
)

MAX_CHARS = 120
REFUSALS = ("unknown", "i do not", "i'm not", "as an ai", "sorry", "cannot")

_lock = threading.Lock()


def clean(reply: str) -> str:
    """The gloss, or "" if the model declined or drifted out of the requested format."""
    text = " ".join(reply.strip().split())
    if not text or len(text) > MAX_CHARS:
        return ""
    low = text.lower()
    if any(low.startswith(r) or low == r for r in REFUSALS):
        return ""
    return text.strip(" .;:\"'")


def ask(host: str, model: str, iast: str, deva: str, timeout: int = 120) -> str:
    body = json.dumps({
        "model": model,
        "stream": False,
        "options": {"temperature": 0},          # deterministic: same input, same gloss
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"Sanskrit stem: {iast} ({deva})"}],
    }).encode("utf-8")
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("message", {}).get("content", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="stop after N new words (smoke test)")
    args = ap.parse_args()

    if not LEMMAS.exists():
        print(f"ERROR: {LEMMAS.name} not found next to this script.")
        return 1

    rows = []
    with LEMMAS.open(encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                rows.append(tuple(parts))

    done: dict[str, str] = {}
    if OUT.exists():
        try:
            done = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            done = {}

    todo = [r for r in rows if r[0] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"lemmas: {len(rows):,}   already done: {len(done):,}   to generate: {len(todo):,}")
    if not todo:
        print("nothing to do.")
        return 0

    try:
        ask(args.host, args.model, "dharma", "धर्म", timeout=180)
    except urllib.error.URLError as exc:
        print(f"\nERROR: cannot reach Ollama at {args.host} ({exc}).")
        print("Start it with:  ollama serve      and pull the model:  ollama pull " + args.model)
        return 1

    work: queue.Queue = queue.Queue()
    for r in todo:
        work.put(r)
    counter = {"n": 0}
    t0 = time.time()

    def worker() -> None:
        while True:
            try:
                slp1, iast, deva = work.get_nowait()
            except queue.Empty:
                return
            try:
                gloss = clean(ask(args.host, args.model, iast, deva))
            except Exception:                    # noqa: BLE001 — one bad word must not end the run
                gloss = ""
            with _lock:
                done[slp1] = gloss
                counter["n"] += 1
                n = counter["n"]
                if n % 200 == 0 or n == len(todo):
                    OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
                    rate = n / max(time.time() - t0, 1e-9)
                    left = (len(todo) - n) / max(rate, 1e-9) / 3600
                    print(f"  {n:,}/{len(todo):,}   {rate:.1f}/s   ~{left:.1f}h remaining",
                          flush=True)
            work.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    for t in threads:
        t.start()
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\ninterrupted — saving progress; re-run to resume")
    with _lock:
        OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")

    usable = sum(1 for g in done.values() if g)
    print(f"\ndone. {len(done):,} lemmas asked, {usable:,} usable glosses "
          f"({len(done) - usable:,} refusals) -> {OUT.name}")
    print("Send llm_sense.json back to be loaded into the engine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
