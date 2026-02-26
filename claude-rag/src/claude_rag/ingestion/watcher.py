"""File-system watcher for the Claude Code RAG system.

Monitors configured directories for ``.md`` and ``.json`` file changes and
triggers the ingestion pipeline with configurable debouncing.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from claude_rag.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)

# File extensions that trigger ingestion
_WATCHED_EXTENSIONS: frozenset[str] = frozenset({".md", ".json"})


class _ChangeHandler(FileSystemEventHandler):
    """Internal watchdog handler that delegates to the watcher's callback.

    Filters events to only ``.md`` and ``.json`` file creations and
    modifications, then forwards the absolute file path to the parent
    ``MemoryFileWatcher`` for debounced processing.

    Args:
        callback: Callable accepting a single *file_path* string argument.
    """

    def __init__(self, callback: callable) -> None:
        super().__init__()
        self._callback = callback

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file-created events.

        Args:
            event: The watchdog file-system event.
        """
        if event.is_directory:
            return
        self._maybe_dispatch(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        """Handle file-modified events.

        Args:
            event: The watchdog file-system event.
        """
        if event.is_directory:
            return
        self._maybe_dispatch(event.src_path)

    def _maybe_dispatch(self, src_path: str) -> None:
        """Forward the event if the file has a watched extension.

        Args:
            src_path: Absolute path to the changed file.
        """
        path = Path(src_path)
        if path.suffix.lower() in _WATCHED_EXTENSIONS:
            logger.debug("Watched file event: %s", src_path)
            self._callback(src_path)


class MemoryFileWatcher:
    """Watches directories for memory-file changes and triggers ingestion.

    Uses the ``watchdog`` library to observe file-system events in one or
    more directories.  Events are debounced per-file so that rapid
    successive saves do not cause redundant ingestion runs.

    Args:
        directories: List of directory paths to watch.
        pipeline: The ``IngestionPipeline`` instance used to process
            changed files.
        debounce_ms: Minimum interval between ingestion runs for the same
            file, in milliseconds.  Defaults to ``500``.
    """

    def __init__(
        self,
        directories: list[str],
        pipeline: IngestionPipeline,
        debounce_ms: int = 500,
    ) -> None:
        self._directories = [str(Path(d).resolve()) for d in directories]
        self._pipeline = pipeline
        self._debounce_s = debounce_ms / 1_000.0

        # Per-file state for debouncing
        self._last_event_time: dict[str, float] = {}
        self._pending_timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

        # Watchdog observers (one per directory)
        self._observers: list[Observer] = []
        self._running = False

        logger.info(
            "MemoryFileWatcher created (directories=%s, debounce_ms=%d)",
            self._directories,
            debounce_ms,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start watching all configured directories.

        This method is non-blocking; each directory gets its own observer
        thread managed by ``watchdog``.

        Raises:
            RuntimeError: If the watcher is already running.
        """
        if self._running:
            raise RuntimeError("MemoryFileWatcher is already running")

        handler = _ChangeHandler(callback=self._on_file_changed)

        for dir_path in self._directories:
            resolved = Path(dir_path)
            if not resolved.is_dir():
                logger.warning("Skipping non-existent directory: %s", dir_path)
                continue

            observer = Observer()
            observer.schedule(handler, str(resolved), recursive=True)
            observer.start()
            self._observers.append(observer)
            logger.info("Watching directory: %s", resolved)

        self._running = True
        logger.info("MemoryFileWatcher started (%d observers)", len(self._observers))

    def stop(self) -> None:
        """Stop all observers and cancel pending debounce timers.

        Blocks until every observer thread has joined.
        """
        if not self._running:
            return

        logger.info("Stopping MemoryFileWatcher...")

        # Cancel all pending debounce timers
        with self._lock:
            for timer in self._pending_timers.values():
                timer.cancel()
            self._pending_timers.clear()

        # Stop and join all observers
        for observer in self._observers:
            observer.stop()
        for observer in self._observers:
            observer.join()

        self._observers.clear()
        self._running = False
        logger.info("MemoryFileWatcher stopped")

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_file_changed(self, file_path: str) -> None:
        """Handle a file change event with debouncing.

        Records the event timestamp and schedules ingestion after the
        debounce interval.  If another event arrives for the same file
        within the interval, the previous timer is cancelled and a new
        one is started.

        Args:
            file_path: Absolute path to the changed file.
        """
        resolved = str(Path(file_path).resolve())
        now = time.monotonic()

        with self._lock:
            self._last_event_time[resolved] = now

            # Cancel any existing timer for this file
            existing_timer = self._pending_timers.pop(resolved, None)
            if existing_timer is not None:
                existing_timer.cancel()

            # Schedule a new timer
            timer = threading.Timer(
                self._debounce_s,
                self._process_file,
                args=(resolved, now),
            )
            timer.daemon = True
            timer.name = f"debounce-{Path(resolved).name}"
            self._pending_timers[resolved] = timer
            timer.start()

        logger.debug("Debounce timer set for %s (%.0f ms)", resolved, self._debounce_s * 1_000)

    def _process_file(self, file_path: str, event_time: float) -> None:
        """Run ingestion for a file after the debounce window expires.

        If a newer event has arrived for the same file since *event_time*,
        this invocation is silently skipped — a newer timer will handle it.

        Args:
            file_path: Absolute path to the file to ingest.
            event_time: Monotonic timestamp of the event that scheduled this
                invocation.
        """
        with self._lock:
            # Check if a newer event supersedes this one
            latest = self._last_event_time.get(file_path, 0.0)
            if latest > event_time:
                logger.debug("Skipping stale event for %s", file_path)
                return
            # Clean up the timer reference
            self._pending_timers.pop(file_path, None)

        logger.info("Processing file change: %s", file_path)

        try:
            result = self._pipeline.ingest_file(file_path)
            if result.skipped:
                logger.info(
                    "File unchanged, ingestion skipped: %s (source_id=%d)",
                    file_path,
                    result.source_id,
                )
            else:
                logger.info(
                    "Ingestion complete: %s — %d chunks in %.1f ms",
                    file_path,
                    result.chunks_created,
                    result.duration_ms,
                )
        except Exception:
            logger.exception("Failed to ingest %s", file_path)
