"""SQLite-backed async queue for hook event processing (T-H5).

Hooks must complete in <500 ms to avoid slowing Claude Code.  This queue
lets hooks enqueue events instantly while a background worker handles the
heavy parse/chunk/embed/store pipeline.

The queue database lives at ``~/.claude-rag/hook_queue.db`` by default
(overridden via ``Config.STATE_DIR``).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS hook_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    session_id TEXT,
    payload TEXT NOT NULL,
    staging_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    processed_at REAL,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON hook_queue(status);
"""


@dataclass
class QueueItem:
    """A single queued hook event.

    Attributes:
        id: Auto-incremented row id.
        event_type: One of ``read``, ``bash``, ``grep``, ``user_prompt``,
            ``session_end``.
        session_id: Claude Code session identifier.
        payload: JSON-encoded event data.
        staging_path: Path to the staging ``.md`` file (if any).
        status: ``pending``, ``processing``, ``done``, or ``error``.
        created_at: Epoch timestamp when the item was enqueued.
    """

    id: int
    event_type: str
    session_id: str | None
    payload: str
    staging_path: str | None
    status: str
    created_at: float


class HookQueue:
    """Thread-safe SQLite queue for hook events.

    Args:
        db_path: Path to the SQLite database file.  Parent directories are
            created automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.debug("HookQueue opened at %s", self._db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        event_type: str,
        payload: dict,
        session_id: str | None = None,
        staging_path: str | None = None,
    ) -> int:
        """Add an event to the queue.

        Args:
            event_type: Category string (``read``, ``bash``, etc.).
            payload: Arbitrary dict that will be JSON-serialised.
            session_id: Optional Claude Code session id.
            staging_path: Optional path to a staging markdown file.

        Returns:
            The auto-incremented row id.
        """
        cur = self._conn.execute(
            "INSERT INTO hook_queue (event_type, session_id, payload, staging_path, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (event_type, session_id, json.dumps(payload), staging_path, time.time()),
        )
        self._conn.commit()
        row_id = cur.lastrowid
        logger.debug("Enqueued %s event (id=%d)", event_type, row_id)
        return row_id

    def dequeue(self) -> Optional[QueueItem]:
        """Claim the oldest pending item, setting its status to ``processing``.

        Returns:
            A ``QueueItem`` or ``None`` if the queue is empty.
        """
        cur = self._conn.execute(
            "UPDATE hook_queue SET status = 'processing' "
            "WHERE id = (SELECT id FROM hook_queue WHERE status = 'pending' ORDER BY id LIMIT 1) "
            "RETURNING id, event_type, session_id, payload, staging_path, status, created_at"
        )
        row = cur.fetchone()
        self._conn.commit()
        if row is None:
            return None
        return QueueItem(*row)

    def complete(self, item_id: int) -> None:
        """Mark an item as successfully processed.

        Args:
            item_id: Row id of the item to mark.
        """
        self._conn.execute(
            "UPDATE hook_queue SET status = 'done', processed_at = ? WHERE id = ?",
            (time.time(), item_id),
        )
        self._conn.commit()

    def fail(self, item_id: int, error_message: str) -> None:
        """Mark an item as failed.

        Args:
            item_id: Row id of the item.
            error_message: Description of the failure.
        """
        self._conn.execute(
            "UPDATE hook_queue SET status = 'error', processed_at = ?, error_message = ? WHERE id = ?",
            (time.time(), error_message, item_id),
        )
        self._conn.commit()

    def pending_count(self) -> int:
        """Return the number of items still waiting to be processed."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM hook_queue WHERE status = 'pending'"
        )
        return cur.fetchone()[0]

    def stats(self) -> dict[str, int]:
        """Return counts grouped by status."""
        cur = self._conn.execute(
            "SELECT status, COUNT(*) FROM hook_queue GROUP BY status"
        )
        return dict(cur.fetchall())

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> HookQueue:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
