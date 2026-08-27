# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Render graph.json → a standalone graph.html (the kāraka dependency graph).

Pure Python string templating + inline SVG. No external libraries, no server:
open graph.html directly. The verb sits at the centre; each argument links to it
with an edge labelled by its kāraka (semantic role).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

HERE = Path(__file__).parent

# kāraka role → (display label, colour)
ROLE_STYLE = {
    "kartā": ("kartā · agent", "#e0a458"),
    "karma": ("karma · object", "#4fb3a6"),
    "karaṇa": ("karaṇa · instrument", "#a982c9"),
    "sampradāna": ("sampradāna · recipient", "#6499e0"),
    "apādāna": ("apādāna · source", "#e07a7a"),
    "adhikaraṇa": ("adhikaraṇa · locus", "#c98a5a"),
}


def iast(slp1: str) -> str:
    return transliterate(slp1, sanscript.SLP1, sanscript.IAST)


def render(graph: dict) -> str:
    W, H = 940, 600
    cx, cy = W / 2, H * 0.60          # verb anchor (centre, slightly low)
    R = 235                            # argument orbit radius

    nodes = {n["id"]: n for n in graph["nodes"]}
    verb_ids = [n["id"] for n in graph["nodes"] if n.get("pos") == "verb"]
    verb_id = verb_ids[0] if verb_ids else graph["nodes"][-1]["id"]
    args = [n for n in graph["nodes"] if n["id"] != verb_id]

    # place arguments on an arc across the top hemisphere
    pos = {verb_id: (cx, cy)}
    if args:
        span = math.radians(150)
        start = math.radians(-165)
        step = span / max(len(args) - 1, 1)
        for i, n in enumerate(args):
            ang = start + i * step
            pos[n["id"]] = (cx + R * math.cos(ang), cy + R * math.sin(ang) * 0.82)

    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="graph">']
    svg.append('<defs>')
    for role, (_, colour) in ROLE_STYLE.items():
        svg.append(
            f'<marker id="arw-{role}" markerWidth="11" markerHeight="11" refX="9" refY="4" '
            f'orient="auto"><path d="M0,0 L9,4 L0,8 Z" fill="{colour}"/></marker>'
        )
    svg.append('</defs>')

    # edges (draw first, under nodes)
    for e in graph["edges"]:
        x1, y1 = pos[e["dependent"]]
        x2, y2 = pos[e["head"]]
        label, colour = ROLE_STYLE.get(e["role"], (e["role"], "#8892a0"))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 26     # control point for a gentle curve
        svg.append(
            f'<path d="M{x1:.0f},{y1:.0f} Q{mx:.0f},{my:.0f} {x2:.0f},{y2:.0f}" '
            f'fill="none" stroke="{colour}" stroke-width="2.5" opacity="0.85" '
            f'marker-end="url(#arw-{e["role"]})"/>'
        )
        lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 20
        svg.append(
            f'<rect x="{lx-58:.0f}" y="{ly-13:.0f}" width="116" height="22" rx="11" '
            f'fill="{colour}" opacity="0.14"/>'
        )
        svg.append(
            f'<text x="{lx:.0f}" y="{ly+3:.0f}" text-anchor="middle" class="role" '
            f'fill="{colour}">{label}</text>'
        )

    # nodes
    for n in graph["nodes"]:
        x, y = pos[n["id"]]
        is_verb = n["id"] == verb_id
        feats = n.get("features", {})
        sub = feats.get("case") or feats.get("tense") or n.get("pos", "")
        fill = "#2c2f3a" if is_verb else "#232631"
        stroke = "#e0a458" if is_verb else "#3a3f4d"
        svg.append(f'<g class="node">')
        svg.append(
            f'<rect x="{x-72:.0f}" y="{y-42:.0f}" width="144" height="84" rx="14" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{2.5 if is_verb else 1.5}"/>'
        )
        svg.append(f'<text x="{x:.0f}" y="{y-8:.0f}" text-anchor="middle" class="deva">{n["surface"]}</text>')
        svg.append(f'<text x="{x:.0f}" y="{y+13:.0f}" text-anchor="middle" class="iast">{iast(n.get("lemma") or "")}</text>')
        svg.append(f'<text x="{x:.0f}" y="{y+30:.0f}" text-anchor="middle" class="feat">{sub}</text>')
        svg.append('</g>')

    svg.append('</svg>')

    legend = " ".join(
        f'<span class="chip"><i style="background:{c}"></i>{l}</span>'
        for l, c in ROLE_STYLE.values()
    )
    sentence = graph["sentence_devanagari"]
    sent_iast = iast(graph["sentence_slp1"])

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kāraka graph</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#1a1c24; color:#e8eaf0;
         font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }}
  h1 {{ font-weight:600; font-size:15px; letter-spacing:.14em; text-transform:uppercase;
        color:#8892a0; margin:0 0 20px; }}
  .sentence {{ font-size:38px; margin:0 0 4px; }}
  .sentence .tl {{ font-size:17px; color:#9aa2b0; font-style:italic; }}
  .graph {{ width:100%; height:auto; margin-top:8px; }}
  .deva {{ font-size:26px; fill:#f2f4f8; }}
  .iast {{ font-size:13px; fill:#aeb6c4; font-style:italic; }}
  .feat {{ font-size:11px; fill:#7f8998; letter-spacing:.04em; }}
  .role {{ font-size:12px; font-weight:600; }}
  .legend {{ display:flex; gap:18px; flex-wrap:wrap; margin-top:14px;
             padding-top:18px; border-top:1px solid #2a2e39; }}
  .chip {{ display:flex; align-items:center; gap:7px; font-size:13px; color:#c4ccd8; }}
  .chip i {{ width:11px; height:11px; border-radius:3px; display:inline-block; }}
  .foot {{ margin-top:20px; font-size:12px; color:#6b7482; }}
</style></head><body><div class="wrap">
  <h1>Kāraka Dependency Graph</h1>
  <div class="sentence">{sentence} &nbsp;<span class="tl">{sent_iast}</span></div>
  {''.join(svg)}
  <div class="legend">{legend}</div>
  <div class="foot">Deterministic core — segmentation + Pāṇinian morphology + case→kāraka rules. No training data.</div>
</div></body></html>"""


if __name__ == "__main__":
    graph = json.loads((HERE / "graph.json").read_text(encoding="utf-8"))
    out = HERE / "graph.html"
    out.write_text(render(graph), encoding="utf-8")
    print(f"✓ wrote {out.name}")
