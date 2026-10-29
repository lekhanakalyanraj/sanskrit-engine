# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Pronunciation — Sanskrit as an English speaker can actually say it.

Deterministic, like everything else in the core: Sanskrit phonology is completely regular, so this
is a transliteration table plus two prosodic rules, not a model.

    pronounce("gacCati")   →  GUCH-chuh-ti
    pronounce("BagavAn")   →  bhu-gu-VAAN

**Why respell at all.** IAST is precise and misleading to a reader who does not know it: `a` is not
"ah", `c` is not "k", `ṣ` and `ś` are not the same sound, and the diacritics that carry all of that
are exactly what an untrained eye skips. The single worst trap is short `a` — it is the vowel in
English "but", not the one in "father", so `dharma` is DHUR-muh and not DAR-mah. A reader who takes
`a` at face value mispronounces the most common vowel in the language.

**On stress — read this before trusting the capitals.** Classical Sanskrit has no phonemic stress.
What is marked here is the Latin-derived convention Western pedagogy teaches (Whitney, Coulson):
stress the penult when it is heavy, otherwise the antepenult. It is a reading aid, not a fact about
the language, and it disagrees with common recitation in places — `bhagavān` comes out BHU-gu-vaan
where reciters usually say bhu-gu-VAAN.

It is also NOT the Vedic pitch accent (udātta / anudātta / svarita). That is a different system, it
is marked in the saṃhitās, and it cannot be recovered from classical orthography — so for an
accented Vedic text this guide is simply the wrong tool.
"""
from __future__ import annotations

from dataclasses import dataclass

#: SLP1 vowel → English respelling. The gloss is what the reader is told the vowel sounds like.
VOWELS: dict[str, tuple[str, str]] = {
    "a": ("u", "as in but"),          "A": ("aa", "as in father"),
    "i": ("i", "as in bit"),          "I": ("ee", "as in feet"),
    "u": ("u", "as in put"),          "U": ("oo", "as in boot"),
    "f": ("ri", "as in rich"),        "F": ("ree", "long ri"),
    "x": ("li", "as in lick"),        "X": ("lee", "long li"),
    "e": ("ay", "as in they"),        "E": ("ai", "as in aisle"),
    "o": ("oh", "as in go"),          "O": ("au", "as in cow"),
}

#: SLP1 consonant → English respelling. Aspirates keep their h — it is a real, audible puff of air,
#: and dropping it changes the word (`bala` strength vs `bhala` — a different consonant entirely).
CONSONANTS: dict[str, str] = {
    "k": "k",  "K": "kh", "g": "g",  "G": "gh", "N": "ng",
    "c": "ch", "C": "chh", "j": "j", "J": "jh", "Y": "ny",
    "w": "t",  "W": "th", "q": "d",  "Q": "dh", "R": "n",     # retroflex — tongue curled back
    "t": "t",  "T": "th", "d": "d",  "D": "dh", "n": "n",     # dental — tongue on the teeth
    "p": "p",  "P": "ph", "b": "b",  "B": "bh", "m": "m",
    "y": "y",  "r": "r",  "l": "l",  "v": "v",
    "S": "sh", "z": "sh", "s": "s",  "h": "h",
    "M": "m",                                                  # anusvāra — nasalises what precedes
    "H": "h",                                                  # visarga — a soft breath
}

_VOWEL_SET = frozenset(VOWELS)
_LONG = frozenset("AIUFXeEoO")


@dataclass
class Pronunciation:
    respelling: str          # "GUCH-chuh-ti"
    syllables: list[str]     # SLP1 syllables, e.g. ["gac", "Ca", "ti"]
    stress: int              # index into syllables, or -1 when there is nothing to stress
    notes: list[str]         # sounds with no English equivalent, worth telling the reader about


#: Sanskrit onsets may begin with a stop or sibilant and end in a semivowel — `tra`, `kra`, `sva`,
#: `dhya`. Those clusters are NOT split, or the respelling misplaces the consonant (`pu-tra`, not
#: `put-ra`).
_SEMIVOWELS = frozenset("yrlv")


def syllabify(word: str) -> list[str]:
    """Split for RESPELLING — one vowel each, with onset clusters kept together.

    Note this is deliberately NOT the akshara division used for metre. Traditional aksharas attach
    consonants forward (`karma` → `ka` + `rma`), which is right for scansion and wrong for telling
    an English reader where the sounds fall — they need `kar-ma`. `core.recite` uses Vidyut's
    akshara division for weight and metre; this one exists only to place sounds for a reader, and
    the two disagreeing is correct rather than a bug.

    A single consonant between vowels opens the next syllable (`ma-ti`); a cluster splits, except
    when it ends in a semivowel and so forms a legal onset (`pu-tra`, `kSe-tre`).
    """
    positions = [i for i, ch in enumerate(word) if ch in _VOWEL_SET]
    if not positions:
        return [word] if word else []
    out: list[str] = []
    start = 0
    for n, pos in enumerate(positions):
        if n + 1 == len(positions):
            out.append(word[start:])
            break
        gap = word[pos + 1:positions[n + 1]]
        if len(gap) >= 2 and gap[-1] in _SEMIVOWELS:
            keep = len(gap) - 2                   # stop+semivowel is one onset: pu|tra, SAs|tra
        elif len(gap) >= 2:
            keep = len(gap) - 1                   # ordinary cluster splits: gac|Ca, an|nam
        else:
            keep = 0                              # a lone consonant opens the next syllable
        end = pos + 1 + keep
        out.append(word[start:end])
        start = end
    return [s for s in out if s]


def is_heavy(syllable: str) -> bool:
    """Guru if the vowel is long, or a short vowel is closed by a consonant (incl. M / H)."""
    vowels = [c for c in syllable if c in _VOWEL_SET]
    if not vowels:
        return True
    if vowels[-1] in _LONG:
        return True
    tail = syllable[syllable.rindex(vowels[-1]) + 1:]
    return bool(tail)


def stress_index(syllables: list[str]) -> int:
    """Penult if heavy, else antepenult — the conventional recitation rule (see module docstring)."""
    n = len(syllables)
    if n <= 1:
        return 0 if n else -1
    if n == 2:
        return 0
    return n - 2 if is_heavy(syllables[n - 2]) else n - 3


def _respell_syllable(syllable: str) -> str:
    out = []
    for ch in syllable:
        if ch in VOWELS:
            out.append(VOWELS[ch][0])
        elif ch in CONSONANTS:
            out.append(CONSONANTS[ch])
    text = "".join(out)
    # A short `a` spelt "u" at the END of any syllable invites the wrong vowel — `khādati` as
    # "KHAA-du-ti" reads *doo*, and `dharma` as "DHUR-mu" reads *moo*. "uh" is unambiguous. This
    # applies medially too, which the first version missed.
    if syllable.endswith("a") and text.endswith("u"):
        text += "h"
    return text


#: Sounds English simply does not have. Naming them is more honest than a respelling that pretends.
_NOTES = {
    "w": "ṭ, ḍ, ṇ are retroflex — say them with the tongue curled back to the roof of the mouth",
    "W": "ṭ, ḍ, ṇ are retroflex — say them with the tongue curled back to the roof of the mouth",
    "q": "ṭ, ḍ, ṇ are retroflex — say them with the tongue curled back to the roof of the mouth",
    "Q": "ṭ, ḍ, ṇ are retroflex — say them with the tongue curled back to the roof of the mouth",
    "R": "ṭ, ḍ, ṇ are retroflex — say them with the tongue curled back to the roof of the mouth",
    "f": "ṛ is a vowel here, roughly the 'ri' of 'rich' — not a separate r plus i",
    "M": "ṃ nasalises the vowel before it rather than adding a full m",
    "H": "ḥ is a soft echo of the preceding vowel, not a hard English h",
}


def pronounce(word_slp1: str) -> Pronunciation:
    """English respelling with the stressed syllable capitalised."""
    syllables = syllabify(word_slp1)
    if not syllables:
        return Pronunciation("", [], -1, [])
    stress = stress_index(syllables)
    parts = [_respell_syllable(s) for s in syllables]
    if 0 <= stress < len(parts):
        parts[stress] = parts[stress].upper()
    notes = list(dict.fromkeys(_NOTES[c] for c in word_slp1 if c in _NOTES))
    return Pronunciation("-".join(p for p in parts if p), syllables, stress, notes)
