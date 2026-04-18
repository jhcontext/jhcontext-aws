"""SQLite-backed offline queue for PAC-AI envelopes.

Used by the offline healthcare scenarios to simulate the
"offline-capable envelopes with deferred synchronisation" story:
envelopes queue locally during connectivity outages and drain to the
upstream API when the uplink returns. On drain the SyncManager verifies
the predecessor-hash chain, detects tampering, and flags late arrivals.

Schema:
    pending_envelopes   one row per envelope emitted at a handoff
    sync_log            append-only event log (queued / synced / tampered / ...)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class QueuedEnvelope:
    envelope_id: int
    context_id: str
    step_name: str
    envelope_json: str
    prov_ttl: str
    predecessor_hash: str | None
    content_hash: str
    queued_at: str
    synced_at: str | None
    drain_status: str  # pending | synced | tampered | chain_broken | late


@dataclass
class SyncLogEntry:
    id: int
    event_type: str
    context_id: str | None
    envelope_id: int | None
    timestamp: str
    details: str | None


class OfflineQueue:
    """Local-first SQLite queue for envelopes emitted while offline."""

    def __init__(self, db_path: Path | str, *, reset: bool = False) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.db_path.exists():
            self.db_path.unlink()
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _create_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_envelopes (
                envelope_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id       TEXT NOT NULL,
                step_name        TEXT NOT NULL,
                envelope_json    TEXT NOT NULL,
                prov_ttl         TEXT NOT NULL,
                predecessor_hash TEXT,
                content_hash     TEXT NOT NULL,
                queued_at        TEXT NOT NULL,
                synced_at        TEXT,
                drain_status     TEXT NOT NULL DEFAULT 'pending'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                context_id  TEXT,
                envelope_id INTEGER,
                timestamp   TEXT NOT NULL,
                details     TEXT
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_status "
            "ON pending_envelopes (drain_status, queued_at)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write path: producing-side enqueue
    # ------------------------------------------------------------------
    def enqueue(
        self,
        *,
        context_id: str,
        step_name: str,
        envelope_json: str,
        prov_ttl: str,
        content_hash: str,
        predecessor_hash: str | None = None,
        queued_at: str | None = None,
    ) -> int:
        queued_at = queued_at or datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_envelopes
                (context_id, step_name, envelope_json, prov_ttl,
                 predecessor_hash, content_hash, queued_at, drain_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                context_id, step_name, envelope_json, prov_ttl,
                predecessor_hash, content_hash, queued_at,
            ),
        )
        envelope_id = cur.lastrowid
        self._log(
            event_type="queued",
            context_id=context_id,
            envelope_id=envelope_id,
            timestamp=queued_at,
            details=json.dumps({"step": step_name}),
        )
        self._conn.commit()
        return envelope_id

    # ------------------------------------------------------------------
    # Read path: drain-side queries
    # ------------------------------------------------------------------
    def pending(self) -> list[QueuedEnvelope]:
        return self._fetch(
            "SELECT * FROM pending_envelopes WHERE drain_status='pending' "
            "ORDER BY queued_at, envelope_id"
        )

    def pending_count(self) -> int:
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT COUNT(*) AS n FROM pending_envelopes WHERE drain_status='pending'"
        ).fetchone()
        return int(row["n"])

    def mark_synced(self, envelope_id: int, *, synced_at: str | None = None) -> None:
        synced_at = synced_at or datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE pending_envelopes SET drain_status='synced', synced_at=? "
            "WHERE envelope_id=?",
            (synced_at, envelope_id),
        )
        self._conn.commit()

    def mark_status(self, envelope_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE pending_envelopes SET drain_status=? WHERE envelope_id=?",
            (status, envelope_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Sync-log helpers
    # ------------------------------------------------------------------
    def log_event(
        self,
        event_type: str,
        *,
        context_id: str | None = None,
        envelope_id: int | None = None,
        timestamp: str | None = None,
        details: Any = None,
    ) -> None:
        self._log(
            event_type=event_type,
            context_id=context_id,
            envelope_id=envelope_id,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            details=json.dumps(details) if details is not None else None,
        )
        self._conn.commit()

    def log(self) -> list[SyncLogEntry]:
        cur = self._conn.cursor()
        rows = cur.execute("SELECT * FROM sync_log ORDER BY id").fetchall()
        return [
            SyncLogEntry(
                id=r["id"],
                event_type=r["event_type"],
                context_id=r["context_id"],
                envelope_id=r["envelope_id"],
                timestamp=r["timestamp"],
                details=r["details"],
            )
            for r in rows
        ]

    def log_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "context_id": e.context_id,
                "envelope_id": e.envelope_id,
                "timestamp": e.timestamp,
                "details": json.loads(e.details) if e.details else None,
            }
            for e in self.log()
        ]

    def summary(self) -> dict[str, int]:
        cur = self._conn.cursor()
        row = cur.execute(
            """
            SELECT
              SUM(CASE WHEN drain_status='pending'       THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN drain_status='synced'        THEN 1 ELSE 0 END) AS synced,
              SUM(CASE WHEN drain_status='tampered'      THEN 1 ELSE 0 END) AS tampered,
              SUM(CASE WHEN drain_status='chain_broken'  THEN 1 ELSE 0 END) AS chain_broken,
              SUM(CASE WHEN drain_status='late'          THEN 1 ELSE 0 END) AS late,
              COUNT(*)                                                        AS total
            FROM pending_envelopes
            """
        ).fetchone()
        return {k: int(row[k] or 0) for k in row.keys()}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _log(
        self,
        *,
        event_type: str,
        context_id: str | None,
        envelope_id: int | None,
        timestamp: str,
        details: str | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO sync_log (event_type, context_id, envelope_id, timestamp, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_type, context_id, envelope_id, timestamp, details),
        )

    def _fetch(self, sql: str) -> list[QueuedEnvelope]:
        cur = self._conn.cursor()
        rows = cur.execute(sql).fetchall()
        return [
            QueuedEnvelope(
                envelope_id=r["envelope_id"],
                context_id=r["context_id"],
                step_name=r["step_name"],
                envelope_json=r["envelope_json"],
                prov_ttl=r["prov_ttl"],
                predecessor_hash=r["predecessor_hash"],
                content_hash=r["content_hash"],
                queued_at=r["queued_at"],
                synced_at=r["synced_at"],
                drain_status=r["drain_status"],
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> OfflineQueue:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
