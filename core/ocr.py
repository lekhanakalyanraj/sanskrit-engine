# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Image input — OCR, and the lexical correction that makes its output usable.

Devanagari OCR is unreliable in specific, predictable ways, so the engine's job is not to trust it
but to **check it**. We hold a 258k-entry lexicon and a Pāṇinian sandhi splitter; a token that is
not a Sanskrit word and sits one confusable character away from one that is, is almost certainly a
misread. Most OCR pipelines hand you raw text and leave you to spot the damage.

What goes wrong, and why it is predictable:

  * **conjuncts** — `kṣa`, `jña`, `ddha` are ligatures that look nothing like their parts;
  * **vowel signs** — the marks separating i/ī, u/ū, e/ai, o/au are small and are dropped first;
  * **anusvāra vs visarga** — a dot above versus two dots beside, routinely swapped;
  * **shape pairs** — व/ब, घ/ध, भ/म, त/न differ by a stroke.

Those are not random errors, so the suggestions here are not generic edit distance: substitutions
are tried from a confusion set FIRST, and generic edits only as a fallback. A suggestion drawn from
the actual failure mode beats a nearer string that OCR would never have produced.

The backend is deliberately behind one interface. Off-the-shelf OCR does **not** read handwritten
or palm-leaf manuscripts — a published benchmark found every traditional engine failing on
handwritten ślokas — so whatever is plugged in today will be replaced, and the correction layer
below is the part that lasts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .morphology import is_valid_word
from .normalize import to_devanagari, to_slp1
from .segment import _underlying

#: SLP1 pairs a Devanagari reader confuses because the glyphs differ by a stroke or a small mark.
#: Ordered by how often OCR actually makes them, not by how different the letters are.
CONFUSABLE: dict[str, str] = {
    "v": "b", "b": "v",          # व / ब
    "G": "D", "D": "G",          # घ / ध
    "B": "m", "m": "B",          # भ / म
    "t": "n", "n": "t",          # त / न
    "p": "y", "y": "p",          # प / य
    "N": "q", "q": "N",          # ङ / ड
    "i": "I", "I": "i",          # vowel length — the mark is small and drops first
    "u": "U", "U": "u",
    "e": "E", "E": "e",
    "o": "O", "O": "o",
    "M": "H", "H": "M",          # anusvāra ं / visarga ः
    "S": "z", "z": "S", "s": "S",  # श / ष / स
}

_ALPHABET = "aAiIuUfFxXeEoOMHkKgGNcCjJYwWqQRtTdDnpPbBmyrlvSzsh"


@dataclass
class Suspect:
    """A token the lexicon does not recognise, with what it was probably meant to be."""
    token: str                       # SLP1, as OCR gave it
    devanagari: str
    suggestions: list[str] = field(default_factory=list)   # SLP1, lexicon-valid
    reason: str = "not in the lexicon"


@dataclass
class OCRResult:
    text_devanagari: str
    suspects: list[Suspect] = field(default_factory=list)
    backend: str = ""

    @property
    def clean(self) -> bool:
        """Clean means "read something and every word checks out" — NOT merely "no complaints".

        An empty read produces zero suspect tokens, which the first version reported as success.
        A failure that looks identical to a perfect result is worse than an error, so emptiness is
        checked explicitly rather than inferred from an absent complaint.
        """
        return bool(self.text_devanagari.strip()) and not self.suspects

    @property
    def empty(self) -> bool:
        """The backend returned nothing. Distinct from "returned text with problems"."""
        return not self.text_devanagari.strip()


class Backend(Protocol):
    name: str
    def read(self, image_path: str) -> str: ...          # → Devanagari text


def _analyses(word_slp1: str) -> bool:
    """Does this stand on its own as an inflected Sanskrit word?

    Kosha membership is the wrong test: MW lists single letters and fragments, so `banam` "splits"
    into `ba` + `nam` and every misread looks legitimate. A real morphological analysis is the
    stronger signal — `vanam` is a noun, `banam` is `unknown`.

    The token is normalised through `_underlying` first, because the lexicon is keyed on pre-visarga
    padas: OCR gives us the written `rAmaH`, the kosha wants `rAmas`.
    """
    from .morphology import analyze_candidates
    if not word_slp1:
        return False
    form = _underlying(word_slp1) or word_slp1
    return any(c.pos in ("noun", "verb", "particle") for c in analyze_candidates(form))


def suggest(token_slp1: str, *, limit: int = 5) -> list[str]:
    """Words the token was probably meant to be — confusable substitutions that stand alone.

    Only substitutions producing a WHOLE word count. That is the point: a misread is exposed
    precisely when one stroke turns an unanalysable string into a word, and generic edit distance
    would instead return near-strings OCR would never have produced.
    """
    out: list[str] = []
    for i, ch in enumerate(token_slp1):
        alt = CONFUSABLE.get(ch)
        if not alt:
            continue
        cand = token_slp1[:i] + alt + token_slp1[i + 1:]
        if cand not in out and _analyses(cand):
            out.append(cand)
            if len(out) >= limit:
                break
    return out


def validate(text: str) -> list[Suspect]:
    """Tokens that are probably misreads. Pure — no OCR involved, so it is testable on strings.

    A token is suspect when it does not analyse as a word AND either
      * a single confusable substitution makes it one — the signature of a misread; or
      * nothing at all can be made of it.

    A token that only works by SPLITTING is not automatically suspect: sandhi joins words all the
    time and `satyameva` is legitimate. But when a one-stroke change yields a single whole word,
    that is the better account, and it is flagged even though a split existed.
    """
    from .segment import segment

    suspects: list[Suspect] = []
    for chunk in to_slp1(text).split():
        if _analyses(chunk):
            continue
        hints = suggest(chunk)
        if hints:
            suspects.append(Suspect(chunk, to_devanagari(chunk), hints,
                                    "one stroke from a real word — likely a misread"))
            continue
        pieces = segment(chunk)
        if pieces and len(pieces) > 1 and all(_analyses(p) for p in pieces):
            continue                       # genuine sandhi, e.g. satyam + eva
        suspects.append(Suspect(chunk, to_devanagari(chunk), [], "not a recognisable word"))
    return suspects


def read_image(image_path: str, backend: Backend) -> OCRResult:
    """OCR an image, then check every word against the lexicon before anyone reads it."""
    text = backend.read(image_path)
    return OCRResult(text_devanagari=text, suspects=validate(text), backend=backend.name)


class OllamaVision:
    """OCR through a local vision-language model served by Ollama.

    Chosen over a dedicated OCR engine on the evidence: on REAL Devanagari scans, VLMs lead and
    traditional engines collapse — EasyOCR reads 93.6% on synthetic renders and 58.3 on real ones,
    and Tesseract is ineffective on handwriting. Among open models the Qwen-VL family was the
    strongest, beating GPT-5.5 on the same benchmark.

    It also costs nothing extra here: Ollama is already running for the explainer, so this needs no
    new system dependency, no API key, and no image leaving the machine.

    The prompt matters as much as the model. A VLM asked to "read this" will helpfully translate,
    summarise, or explain — all of which destroy the transcription. The instruction below forbids
    exactly that, and the caller still passes everything through `validate()`, because a fluent
    model producing plausible-looking Devanagari is a more dangerous failure than a blank result.
    """

    name = "ollama-vision"

    #: Transcribe, do not interpret. Each clause here is a failure this model actually produces.
    PROMPT = (
        "Transcribe the Sanskrit text in this image into Devanagari script, exactly as printed.\n"
        "Rules:\n"
        "- Output ONLY the Devanagari text. No translation, no transliteration, no commentary.\n"
        "- Preserve line breaks as they appear on the page.\n"
        "- Preserve every vowel mark, anusvāra (ं), visarga (ः) and avagraha (ऽ) exactly.\n"
        "- Do not correct, complete or normalise the text. If a character is unclear, transcribe "
        "what is actually printed rather than what you think it should say.\n"
        "- If you cannot read the image at all, output nothing."
    )

    def __init__(self, model: str = "qwen2.5vl:7b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def read(self, image_path: str) -> str:
        import base64
        import json
        import urllib.error
        import urllib.request

        with open(image_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        payload = json.dumps({
            "model": self.model,
            "prompt": self.PROMPT,
            "images": [encoded],
            "stream": False,
            # near-greedy: transcription has one right answer, so sampling only invents variants
            "options": {"temperature": 0.0},
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self.host}/api/generate", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = json.loads(response.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}. Is it running? "
                f"Pull the model with `ollama pull {self.model}`."
            ) from exc
        return (body.get("response") or "").strip()
