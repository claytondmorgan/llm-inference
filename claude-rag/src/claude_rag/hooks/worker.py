"""Background worker that drains the hook queue (T-H5).

Polls the SQLite queue for pending events and runs each through the
ingestion pipeline (parse -> chunk -> embed -> store).  Staging files
are cleaned up after successful processing.

Usage::

    python -m claude_rag.hooks.worker          # run until Ctrl-C
    python -m claude_rag.hooks.worker --once   # drain queue then exit
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from claude_rag.config import Config
from claude_rag.hooks.queue import HookQueue, QueueItem
from claude_rag.ingestion.pipeline import IngestionPipeline
from claude_rag.monitoring.activity_logger import log_activity

logger = logging.getLogger(__name__)

# Default poll interval in seconds when the queue is empty.
_POLL_INTERVAL = 2.0


class HookWorker:
    """Processes queued hook events through the ingestion pipeline.

    Args:
        config: Application configuration.
        pipeline: Optional pre-built pipeline (constructed lazily if omitted).
        queue: Optional pre-built queue (constructed from config if omitted).
    """

    def __init__(
        self,
        config: Config | None = None,
        pipeline: IngestionPipeline | None = None,
        queue: HookQueue | None = None,
    ) -> None:
        self.config = config or Config()
        self._pipeline = pipeline
        self._queue = queue
        self._running = False

    @property
    def pipeline(self) -> IngestionPipeline:
        if self._pipeline is None:
            self._pipeline = IngestionPipeline(self.config)
        return self._pipeline

    @property
    def queue(self) -> HookQueue:
        if self._queue is None:
            self._queue = HookQueue(self.config.STATE_DIR / "hook_queue.db")
        return self._queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_one(self) -> bool:
        """Claim and process a single queue item.

        Returns:
            ``True`` if an item was processed, ``False`` if the queue was empty.
        """
        item = self.queue.dequeue()
        if item is None:
            return False

        _cid = str(item.id)
        age_s = round(time.time() - item.created_at, 1)

        # -- item_dequeued -----------------------------------------------------
        log_activity(
            "worker", "item_dequeued",
            f"Dequeued item #{item.id} (type={item.event_type}, session={item.session_id}, age={age_s}s).",
            session_id=item.session_id,
            correlation_id=_cid,
            data={"item_id": item.id, "event_type": item.event_type, "age_s": age_s},
        )

        logger.info(
            "Processing queue item %d (%s, session=%s)",
            item.id,
            item.event_type,
            item.session_id,
        )

        try:
            self._ingest_item(item)
            self.queue.complete(item.id)
            logger.info("Completed queue item %d", item.id)
        except Exception as exc:
            self.queue.fail(item.id, str(exc))
            # -- item_failed ---------------------------------------------------
            log_activity(
                "worker", "item_failed",
                f"FAILED item #{item.id}: {exc}. Marked as error.",
                level="error",
                session_id=item.session_id,
                correlation_id=_cid,
                data={"item_id": item.id, "error": str(exc)},
            )
            logger.exception("Failed queue item %d: %s", item.id, exc)

        return True

    def drain(self) -> int:
        """Process all pending items until the queue is empty.

        Returns:
            Number of items processed.
        """
        count = 0
        while self.process_one():
            count += 1
        return count

    def run(self, poll_interval: float = _POLL_INTERVAL) -> None:
        """Run continuously, polling for new items.

        Blocks until ``stop()`` is called or the process is interrupted.

        Args:
            poll_interval: Seconds to sleep when the queue is empty.
        """
        self._running = True
        logger.info("Hook worker started (poll_interval=%.1fs)", poll_interval)

        try:
            while self._running:
                if not self.process_one():
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Hook worker interrupted")
        finally:
            self._running = False
            logger.info("Hook worker stopped")

    def stop(self) -> None:
        """Signal the run loop to exit."""
        self._running = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ingest_item(self, item: QueueItem) -> None:
        """Ingest a single queue item via the pipeline.

        Args:
            item: The dequeued item to process.
        """
        _cid = str(item.id)
        staging_path = item.staging_path
        if not staging_path:
            # -- staging_missing -----------------------------------------------
            log_activity(
                "worker", "staging_missing",
                f"Queue item #{item.id} has no staging_path. Cannot ingest.",
                level="warn",
                session_id=item.session_id,
                correlation_id=_cid,
                data={"item_id": item.id},
            )
            logger.warning("Queue item %d has no staging_path, skipping", item.id)
            return

        path = Path(staging_path)
        if not path.exists():
            # -- staging_missing -----------------------------------------------
            log_activity(
                "worker", "staging_missing",
                f"Staging file missing for item #{item.id}: {staging_path}. Cannot ingest.",
                level="warn",
                session_id=item.session_id,
                correlation_id=_cid,
                data={"item_id": item.id, "staging_path": staging_path},
            )
            logger.warning("Staging file missing: %s (item %d)", staging_path, item.id)
            return

        # -- ingestion_started -------------------------------------------------
        log_activity(
            "worker", "ingestion_started",
            f"Starting pipeline for item #{item.id}: {path.name}",
            session_id=item.session_id,
            correlation_id=_cid,
            data={"item_id": item.id, "staging_path": staging_path},
        )

        result = self.pipeline.ingest_file(staging_path, correlation_id=_cid)

        # -- item_completed ----------------------------------------------------
        log_activity(
            "worker", "item_completed",
            f"Completed item #{item.id}: source_id={result.source_id}, {result.chunks_created} chunks, {result.duration_ms:.0f}ms.",
            session_id=item.session_id,
            correlation_id=_cid,
            data={
                "item_id": item.id,
                "source_id": result.source_id,
                "chunks_created": result.chunks_created,
                "duration_ms": result.duration_ms,
                "skipped": result.skipped,
                "stage_timings": result.stage_timings,
            },
            duration_ms=result.duration_ms,
        )

        logger.info(
            "Ingested %s -> source_id=%d, chunks=%d, %.1f ms",
            staging_path,
            result.source_id,
            result.chunks_created,
            result.duration_ms,
        )

        # Clean up staging file (it's now in the DB)
        if path.exists() and "staging" in str(path):
            path.unlink()
            # -- staging_cleaned -----------------------------------------------
            log_activity(
                "worker", "staging_cleaned",
                f"Cleaned up staging file for item #{item.id}. Content is in DB.",
                session_id=item.session_id,
                correlation_id=_cid,
                data={"item_id": item.id, "staging_path": staging_path},
            )
            logger.debug("Cleaned up staging file: %s", staging_path)


def main() -> None:
    """CLI entry point for the hook worker."""
    parser = argparse.ArgumentParser(description="Claude RAG hook queue worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain the queue once then exit (don't poll)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=_POLL_INTERVAL,
        help=f"Seconds between polls when queue is empty (default: {_POLL_INTERVAL})",
    )
    args = parser.parse_args()

    from claude_rag.logging_config import configure_logging

    config = Config()
    configure_logging(level=config.LOG_LEVEL, log_format="text")

    worker = HookWorker(config)

    if args.once:
        count = worker.drain()
        print(f"Processed {count} item(s).")
    else:
        print(f"Hook worker running (poll every {args.poll_interval}s). Press Ctrl+C to stop.")
        worker.run(poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
