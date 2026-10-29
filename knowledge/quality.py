# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Lekhana Kalyan Raj
"""Data-quality plumbing for the ingests — reconciliation, quarantine, provenance.

Written after a cleaning change silently deleted 5,853 dictionary senses and nothing noticed.
The regex that caused it was one bug; the reason it survived is that the pipeline had no way to
*detect* loss. Each piece here closes one of those holes:

  * `Reconciler`  — every row is accounted for: ``seen == kept + rejected``. An ingest that cannot
    balance its books raises instead of committing. This is the check that would have caught it.
  * `sense_rejected` — rejects are QUARANTINED with a reason code, not dropped. You cannot audit
    what you discarded if you discarded it; recovering those 5,853 meant re-parsing the raw source.
  * `source_meta`  — sha256 + byte count + cleaner version per source. `tasmāt` was stored as
    ") ad. therefore ." long after the cleaner learned to write "therefore", because nothing
    recorded WHICH cleaner had built a row, so nobody knew the table was stale.

None of this validates *meaning* — it validates that the pipeline is honest about what it did.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Bump whenever `clean_for_reading` (or any ingest's own `_clean`) changes what it emits. Rows
#: carry the version that built them, so a stale table is a query rather than a guess.
CLEANER_VERSION = "2026-08-29.2"

#: An ingest losing more than this fraction of its input is assumed broken rather than thorough.
#: Set from observation: the reading pass legitimately drops citation-only fragments, which runs
#: about 4% on Apte and 2% on Macdonell. The bad version dropped 7% of Apte in one change.
DEFAULT_MAX_LOSS = 0.15


def ensure_quality_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sense_rejected (
        source TEXT NOT NULL, lemma TEXT, raw TEXT NOT NULL,
        reason TEXT NOT NULL, cleaner_version TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rej_source ON sense_rejected (source, reason)")
    conn.execute("""CREATE TABLE IF NOT EXISTS source_meta (
        source TEXT PRIMARY KEY, origin TEXT, sha256 TEXT, bytes INTEGER,
        ingested_at TEXT, cleaner_version TEXT,
        rows_seen INTEGER, rows_kept INTEGER, rows_rejected INTEGER)""")


def file_digest(path: Path) -> tuple[str, int]:
    """sha256 + size of a cached source file, so a silent upstream change is detectable."""
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


class ReconciliationError(RuntimeError):
    """Raised when an ingest cannot account for its own rows."""


@dataclass
class Reconciler:
    """Row-conservation accounting for one ingest run.

    The contract is deliberately arithmetic rather than statistical: every input fragment is
    either kept or rejected with a stated reason, and the two must sum to what came in. A
    transform that "just loses some" is indistinguishable from a transform with a bug.
    """

    source: str
    max_loss: float = DEFAULT_MAX_LOSS
    _seen: int = 0
    _kept: int = 0
    rejects: list[tuple[str | None, str, str]] = field(default_factory=list)

    def seen(self, n: int = 1) -> None:
        self._seen += n

    def kept(self, n: int = 1) -> None:
        self._kept += n

    def reject(self, raw: str, reason: str, lemma: str | None = None) -> None:
        """Quarantine one fragment. `reason` is a short stable code, not prose."""
        self.rejects.append((lemma, raw[:400], reason))

    # ── verdict ─────────────────────────────────────────────────────────────────────────────────
    @property
    def loss(self) -> float:
        return len(self.rejects) / self._seen if self._seen else 0.0

    def check(self) -> None:
        counted = self._kept + len(self.rejects)
        if counted != self._seen:
            raise ReconciliationError(
                f"{self.source}: {self._seen:,} seen but {counted:,} accounted for "
                f"({self._kept:,} kept + {len(self.rejects):,} rejected) — "
                f"{self._seen - counted:+,} unexplained")
        if self.loss > self.max_loss:
            top = ", ".join(f"{r}={c}" for r, c in self.reason_counts()[:4])
            raise ReconciliationError(
                f"{self.source}: rejected {self.loss:.1%} of input "
                f"(limit {self.max_loss:.0%}) — top reasons: {top}")

    def reason_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for _, _, reason in self.rejects:
            counts[reason] = counts.get(reason, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    # ── persistence ─────────────────────────────────────────────────────────────────────────────
    def record(self, conn: sqlite3.Connection, origin: str = "", path: Path | None = None) -> None:
        """Write the quarantine rows and this run's provenance. Call AFTER `check()`."""
        ensure_quality_schema(conn)
        conn.execute("DELETE FROM sense_rejected WHERE source = ?", (self.source,))
        conn.executemany(
            "INSERT INTO sense_rejected (source, lemma, raw, reason, cleaner_version) "
            "VALUES (?, ?, ?, ?, ?)",
            [(self.source, lem, raw, reason, CLEANER_VERSION) for lem, raw, reason in self.rejects])
        sha, nbytes = file_digest(path) if path and path.exists() else ("", 0)
        conn.execute(
            "INSERT OR REPLACE INTO source_meta (source, origin, sha256, bytes, ingested_at, "
            "cleaner_version, rows_seen, rows_kept, rows_rejected) VALUES (?,?,?,?,?,?,?,?,?)",
            (self.source, origin, sha, nbytes, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             CLEANER_VERSION, self._seen, self._kept, len(self.rejects)))

    def summary(self) -> str:
        parts = ", ".join(f"{r}={c:,}" for r, c in self.reason_counts()[:5])
        return (f"{self.source}: {self._kept:,} kept / {self._seen:,} seen "
                f"({self.loss:.1%} quarantined){'  [' + parts + ']' if parts else ''}")


def classify_rejection(raw: str, cleaned: str) -> str:
    """Why did this fragment not survive? A stable code, so rejects can be grouped and reviewed."""
    import re
    if not raw.strip():
        return "empty_input"
    if cleaned.strip():
        # Non-empty but still rejected — it failed a LENGTH bar, not the cleaner. Naming this
        # separately matters: the first reconciled run reported 8,395 Apte rejects as reason
        # "kept", which is how a length threshold quietly deleting "Sky" and "Oil" stayed invisible.
        return "too_short"
    if re.fullmatch(r"[\s\d.,;:()\[\]—–-]*", raw):
        return "punctuation_or_number_only"
    if re.search(r"\b(?:cf|q\.\s?v|see|ib|id)\b", raw, re.I) or "=" in raw:
        return "cross_reference"
    if re.fullmatch(r"[\s{}]*", raw):
        return "markup_only"
    if re.match(r"^\s*\{[@%]", raw) or re.fullmatch(r"[^a-zA-Z]*", raw):
        return "markup_only"
    if re.fullmatch(r"[\sA-Za-zĀāĪīŪūŚśṢṣṚṛṆṇḌḍṬṭḤḥṂṃ]{1,4}\.?", raw):
        return "bare_abbreviation"
    return "unknown_check_me"      # deliberately loud: an unclassified reject wants human eyes


def stale_sources(conn: sqlite3.Connection) -> list[str]:
    """Sources whose rows were built by an older cleaner than the one now in the tree."""
    try:
        rows = conn.execute(
            "SELECT source FROM source_meta WHERE cleaner_version != ?", (CLEANER_VERSION,)).fetchall()
    except sqlite3.Error:
        return []
    return [r[0] for r in rows]
