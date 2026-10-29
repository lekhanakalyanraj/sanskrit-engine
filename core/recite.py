# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Chandas — scanning a verse for recitation: syllable weight, pāda structure, metre.

    scan("karmaRyevADikAraste mA Palezu kadAcana")
      → GGGGLGGG / GLGLLGLL, anuṣṭubh (pathyā)

Two sources of truth, deliberately separated:

  * **Fixed-pattern metres** come from `vidyut.chandas` — 145 vṛttas, each one exact weight string
    (`mandAkrAntA` is `GGGG|LLLLLG|GLGGLGG`). Vidyut also does the akshara division, which follows
    the traditional convention (consonants attach forward: `karma` → `ka` + `rma`) rather than any
    English notion of a syllable.

  * **The anuṣṭubh is computed here**, because it cannot be matched. It has no fixed pattern — its
    pādas vary by design and only positions 5–7 are constrained — so pattern lookup returns nothing
    for it. That matters more than it sounds: the anuṣṭubh carries the Gītā, the Rāmāyaṇa, the
    Mahābhārata and most of the Upaniṣads. Vidyut covers 145 metres and misses the one holding most
    of the corpus.

**On strictness.** The classical śloka rule is not the Vedic one. Vedic anuṣṭubh is looser, so a
Saṃhitā or early Upaniṣadic verse can fail the classical constraint while being perfectly correct
in its own tradition — Īśā 1 does exactly that. Deviations are therefore reported as deviations,
never as errors, and a recognised vipulā is named rather than flagged. Declaring a Vedic verse
broken for missing a classical rule would be the metrical form of imposing one tradition's frame on
a text that does not carry it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .normalize import to_slp1

_METERS = Path(__file__).resolve().parent.parent / "vidyut-data" / "chandas" / "meters.tsv"

GURU, LAGHU = "G", "L"

#: A long syllable is held twice as long as a short one. That single fact is the whole of the
#: timing, and it is what the ⏑/— notation encodes without ever saying so.
MATRAS = {GURU: 2, LAGHU: 1}

#: Odd pādas: syllables 5–7 are pathyā or one of the four named vipulās (Macdonell).
#: Even pādas: 5–7 must be ja-gaṇa (L G L) — that is the defining mark of the śloka.
_ODD_FORMS = {"LGG": "pathyā", "LLL": "na-vipulā", "GLL": "bha-vipulā",
              "GGG": "ma-vipulā", "GLG": "ra-vipulā"}
_EVEN_FORM = "LGL"


@dataclass
class Akshara:
    text: str
    weight: str          # "G" or "L"


@dataclass
class Scansion:
    aksharas: list[Akshara]
    pattern: str                       # the whole verse, e.g. "GGGGLGGGGLGLLGLL"
    padas: list[str] = field(default_factory=list)
    metre: str | None = None
    form: str | None = None            # pathyā / a named vipulā / irregular
    notes: list[str] = field(default_factory=list)

    def marks(self) -> str:
        """The pattern in the conventional recitation notation."""
        return "".join("—" if w == GURU else "⏑" for w in self.pattern)

    def matras(self) -> int:
        """Total beats. A pāda's beat count, not its syllable count, is what you hear."""
        return sum(MATRAS[w] for w in self.pattern)

    def read_along(self) -> list[dict]:
        """One entry per pāda, in the form a learner can actually follow.

        `marks()` is notation for people who already read notation — `————⏑———` says nothing about
        what to DO. This says it: which syllables to hold, where to breathe, and how many beats the
        pāda runs to, so the heavy-then-light shape of a śloka is visible as two numbers.

        Syllables come out in IAST rather than SLP1, because this is the one part of the output
        aimed at reading aloud rather than at the machine.
        """
        from .normalize import to_iast

        size = 8 if self.metre == "anuṣṭubh" else len(self.aksharas)
        out: list[dict] = []
        groups = [self.aksharas[i:i + size] for i in range(0, len(self.aksharas), size)] or []
        for n, group in enumerate(groups, start=1):
            out.append({
                "pada": n,
                # a trailing dash marks the syllable it applies to, unlike a detached pattern row
                "syllables": [f"{to_iast(a.text)}{'—' if a.weight == GURU else ''}" for a in group],
                "hold": ["hold" if a.weight == GURU else "quick" for a in group],
                "matras": sum(MATRAS[a.weight] for a in group),
                # a light break between pādas, a full stop at the half-verse and the end
                "pause": "‖" if n % 2 else "‖‖",
            })
        return out


@lru_cache(maxsize=1)
def _chandas():
    from vidyut.chandas import Chandas
    return Chandas.from_text(_METERS.read_text(encoding="utf-8"))


def _aksharas(text_slp1: str) -> list[Akshara]:
    """Syllable division + weight from Vidyut.

    `Chandas.classify` is Rust behind pyo3 and **panics** on non-SLP1 input rather than raising, so
    the conversion is not optional and the guard catches BaseException — a PanicException would
    otherwise take the process down.
    """
    try:
        match = _chandas().classify(text_slp1)
    except BaseException:                                  # noqa: BLE001 — pyo3 PanicException
        return []
    return [Akshara(a.text, GURU if str(a.weight).lower().startswith("g") else LAGHU)
            for line in match.aksharas for a in line]


def _fixed_metre(text_slp1: str) -> str | None:
    try:
        return _chandas().classify(text_slp1).padya or None
    except BaseException:                                  # noqa: BLE001
        return None


def _anustubh(pattern: str) -> tuple[str | None, str | None, list[str]]:
    """Is this an anuṣṭubh? Computed from the rule, since there is no pattern to match.

    Returns (metre, form, notes). A half-verse (16 aksharas) counts: the constraint is per pāda.
    """
    # A half-verse or a full verse, nothing else. Allowing any multiple of 8 let a 24-syllable
    # prose clause — three pādas, which is not an anuṣṭubh unit — qualify by arithmetic accident.
    if len(pattern) not in (16, 32):
        return None, None, []

    forms: list[str] = []
    notes: list[str] = []
    for i in range(0, len(pattern), 8):
        pada, n = pattern[i:i + 8], i // 8 + 1
        key = pada[4:7]
        if n % 2:                                          # odd pāda — pathyā or a vipulā
            form = _ODD_FORMS.get(key)
            if form is None:
                notes.append(f"pāda {n}: syllables 5–7 are {key}, which is neither pathyā nor a "
                             f"named vipulā — regular in Vedic anuṣṭubh, irregular in classical")
                form = "irregular"
        else:                                              # even pāda — must be ja-gaṇa
            if key == _EVEN_FORM:
                form = "pathyā"
            else:
                notes.append(f"pāda {n}: syllables 5–7 are {key}, not the required {_EVEN_FORM}; "
                             f"even pādas are fixed in classical śloka but freer in Vedic")
                form = "irregular"
        forms.append(form)

    # NOT "every pāda must conform" — that was tried and it refused Īśā 1, a real Vedic anuṣṭubh
    # whose second pāda breaks the classical rule. Condemning a Vedic verse for failing a classical
    # constraint is exactly what this module's docstring forbids. The apparent over-detection that
    # prompted the change was a mislabelled corpus: three of the six DCS texts are themselves in
    # verse, so a high rate there is correct.
    if all(f == "irregular" for f in forms):
        return None, None, []                              # nothing metrical about it at all
    named = [f for f in forms if f not in ("pathyā", "irregular")]
    summary = named[0] if named else ("pathyā" if all(f == "pathyā" for f in forms) else "irregular")
    return "anuṣṭubh", summary, notes


def scan(text: str) -> Scansion:
    """Scan a verse: aksharas, weights, pāda split, and the metre where it can be determined."""
    slp1 = to_slp1(text)
    aksharas = _aksharas(slp1)
    if not aksharas:
        return Scansion([], "")
    pattern = "".join(a.weight for a in aksharas)

    metre = _fixed_metre(slp1)
    form, notes = None, []
    if metre is None:
        metre, form, notes = _anustubh(pattern)

    padas = ([pattern[i:i + 8] for i in range(0, len(pattern), 8)]
             if metre == "anuṣṭubh" else [pattern])
    return Scansion(aksharas, pattern, padas, metre, form, notes)


if __name__ == "__main__":
    for label, verse in [
        ("BG 2.47", "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन"),
        ("Īśa 1", "ईशावास्यमिदं सर्वं यत्किञ्च जगत्यां जगत्"),
        ("Meghadūta 1.1", "कश्चित्कान्ताविरहगुरुणा स्वाधिकारात्प्रमत्तः"),
    ]:
        s = scan(verse)
        print(f"\n{label}: {s.metre or '—'}{f' ({s.form})' if s.form else ''}")
        print(f"  {s.marks()}")
        for n in s.notes:
            print(f"  · {n}")
