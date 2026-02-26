"""Tests for the structured logging configuration module."""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.logging_config import JSONFormatter, configure_logging, get_logger


class TestJSONFormatter:
    """Tests for the JSONFormatter class."""

    def test_basic_format(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Hello world"
        assert "timestamp" in data

    def test_exception_info(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="Something failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestConfigureLogging:
    """Tests for configure_logging."""

    def test_json_format(self) -> None:
        configure_logging(level="DEBUG", log_format="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) >= 1

    def test_text_format(self) -> None:
        configure_logging(level="WARNING", log_format="text")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_idempotent(self) -> None:
        configure_logging(level="INFO", log_format="json")
        handler_count_1 = len(logging.getLogger().handlers)
        configure_logging(level="INFO", log_format="json")
        handler_count_2 = len(logging.getLogger().handlers)
        assert handler_count_1 == handler_count_2

    def test_noisy_loggers_suppressed(self) -> None:
        configure_logging(level="DEBUG", log_format="json")
        for name in ("transformers", "sentence_transformers", "torch", "urllib3"):
            assert logging.getLogger(name).level >= logging.WARNING


class TestGetLogger:
    """Tests for get_logger convenience function."""

    def test_returns_logger(self) -> None:
        lg = get_logger("test.module")
        assert isinstance(lg, logging.Logger)
        assert lg.name == "test.module"
