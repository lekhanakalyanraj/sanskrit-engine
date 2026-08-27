# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Demo runner — analyze one sentence and write graph.json (feeds render.py → graph.html).

The Phase-0 logic now lives in the `core/` package; this is kept as a convenience entry point.
For interactive exploration use `playground.py` (Streamlit); for correctness run `pytest`.
"""
import json
from pathlib import Path

from core import analyze_sentence

SENTENCE = "बालः हस्तेन अन्नं खादति"

if __name__ == "__main__":
    result = analyze_sentence(SENTENCE)
    out = Path(__file__).with_name("graph.json")
    out.write_text(json.dumps(result.to_graph_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(SENTENCE)
    for e in result.edges:
        print(f"  {result.tokens[e.dependent].surface} —{e.role}→ {result.tokens[e.head].surface}")
    print(f"✓ wrote {out.name} ({len(result.tokens)} nodes, {len(result.edges)} edges)")
