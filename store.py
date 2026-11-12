"""Persistencia SQLite: evita duplicados, aplica límites y deja auditoría."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed (
    message_id TEXT PRIMARY KEY,
    sender     TEXT NOT NULL,
    subject    TEXT,
    status     TEXT NOT NULL,   -- replied | ignored | failed | rate_limited | dry_run
    detail     TEXT,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processed_sender_ts ON processed(sender, ts);
CREATE INDEX IF NOT EXISTS idx_processed_status_ts ON processed(status, ts);
"""


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def seen(self, message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM processed WHERE message_id = ? AND status != 'failed'",
                (message_id,),
            ).fetchone()
        return row is not None

    def mark(
        self,
        message_id: str,
        sender: str,
        subject: str,
        status: str,
        detail: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO processed "
                "(message_id, sender, subject, status, detail, ts) VALUES (?,?,?,?,?,?)",
                (message_id, sender.lower(), subject[:300], status, detail[:500], time.time()),
            )
            self._conn.commit()

    def replies_since(self, sender: str, seconds: int = 86400) -> int:
        since = time.time() - seconds
        with self._lock:
            (n,) = self._conn.execute(
                "SELECT COUNT(*) FROM processed WHERE sender = ? AND status = 'replied' AND ts >= ?",
                (sender.lower(), since),
            ).fetchone()
        return n

    def total_replies_since(self, seconds: int = 86400) -> int:
        since = time.time() - seconds
        with self._lock:
            (n,) = self._conn.execute(
                "SELECT COUNT(*) FROM processed WHERE status = 'replied' AND ts >= ?",
                (since,),
            ).fetchone()
        return n

    def close(self) -> None:
        with self._lock:
            self._conn.close()
