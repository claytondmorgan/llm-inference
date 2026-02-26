"""Tests for Phase 2A — Hook-Based Real-Time Interception.

Covers the SQLite queue (T-H5), PostToolUse handlers (T-H1/T-H2),
UserPromptSubmit handler (T-H3), session end handler (T-H4), and
the background worker.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from claude_rag.hooks.queue import HookQueue, QueueItem


# =========================================================================
# T-H5: Queue tests
# =========================================================================


class TestHookQueue:
    """Test the SQLite-backed hook queue."""

    @pytest.fixture()
    def queue(self, tmp_path: Path) -> HookQueue:
        q = HookQueue(tmp_path / "test_queue.db")
        yield q
        q.close()

    def test_enqueue_returns_id(self, queue: HookQueue):
        item_id = queue.enqueue("read", {"file": "test.py"}, session_id="s1")
        assert item_id >= 1

    def test_dequeue_returns_pending_item(self, queue: HookQueue):
        queue.enqueue("read", {"file": "a.py"}, session_id="s1")
        item = queue.dequeue()
        assert item is not None
        assert item.event_type == "read"
        assert item.status == "processing"

    def test_dequeue_empty_returns_none(self, queue: HookQueue):
        assert queue.dequeue() is None

    def test_dequeue_fifo_order(self, queue: HookQueue):
        queue.enqueue("read", {"file": "first.py"})
        queue.enqueue("bash", {"cmd": "ls"})
        item1 = queue.dequeue()
        item2 = queue.dequeue()
        assert item1.event_type == "read"
        assert item2.event_type == "bash"

    def test_complete_marks_done(self, queue: HookQueue):
        queue.enqueue("read", {"file": "a.py"})
        item = queue.dequeue()
        queue.complete(item.id)
        stats = queue.stats()
        assert stats.get("done") == 1
        assert stats.get("pending", 0) == 0

    def test_fail_marks_error(self, queue: HookQueue):
        queue.enqueue("read", {"file": "a.py"})
        item = queue.dequeue()
        queue.fail(item.id, "something broke")
        stats = queue.stats()
        assert stats.get("error") == 1

    def test_pending_count(self, queue: HookQueue):
        assert queue.pending_count() == 0
        queue.enqueue("read", {"file": "a.py"})
        queue.enqueue("read", {"file": "b.py"})
        assert queue.pending_count() == 2
        queue.dequeue()
        assert queue.pending_count() == 1

    def test_dequeue_skips_processing_items(self, queue: HookQueue):
        queue.enqueue("read", {"file": "a.py"})
        item = queue.dequeue()  # now "processing"
        assert item is not None
        # Second dequeue should return None (no more pending)
        assert queue.dequeue() is None

    def test_staging_path_stored(self, queue: HookQueue):
        queue.enqueue("read", {"f": "a"}, staging_path="/tmp/staging/read_123.md")
        item = queue.dequeue()
        assert item.staging_path == "/tmp/staging/read_123.md"

    def test_context_manager(self, tmp_path: Path):
        with HookQueue(tmp_path / "ctx_test.db") as q:
            q.enqueue("read", {"f": "a"})
            assert q.pending_count() == 1


# =========================================================================
# T-H1: PostToolUse Read handler
# =========================================================================


class TestPostToolUseRead:
    """Test the Read tool hook handler."""

    def test_handle_read_creates_staging_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.post_tool_use import handle

        event = {
            "session_id": "test-session-1",
            "tool_name": "Read",
            "tool_input": {"file_path": "/home/user/app.py"},
            "tool_response": "def hello():\n    print('world')\n",
        }
        handle(event)

        # Staging file should exist
        staging_files = list((tmp_path / "staging").glob("read_*.md"))
        assert len(staging_files) == 1

        content = staging_files[0].read_text(encoding="utf-8")
        assert "File Read: /home/user/app.py" in content
        assert "def hello():" in content
        assert "test-session-1" in content

        # Queue should have 1 pending item
        queue = HookQueue(tmp_path / "hook_queue.db")
        assert queue.pending_count() == 1
        item = queue.dequeue()
        assert item.event_type == "read"
        assert item.staging_path == str(staging_files[0])
        queue.close()


# =========================================================================
# T-H2: PostToolUse Bash/Grep handlers
# =========================================================================


class TestPostToolUseBash:
    """Test the Bash tool hook handler."""

    def test_handle_bash_creates_staging_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.post_tool_use import handle

        event = {
            "session_id": "test-session-2",
            "tool_name": "Bash",
            "tool_input": {"command": "grep -r 'authentication' src/"},
            "tool_response": "src/auth.py:5: class AuthManager:\nsrc/auth.py:12: def validate_token(self):\n",
        }
        handle(event)

        staging_files = list((tmp_path / "staging").glob("bash_*.md"))
        assert len(staging_files) == 1

        content = staging_files[0].read_text(encoding="utf-8")
        assert "Command Execution" in content
        assert "grep -r 'authentication' src/" in content
        assert "AuthManager" in content

    def test_handle_bash_skips_short_output(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.post_tool_use import handle

        event = {
            "session_id": "test-session-3",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_response": "/home/user",
        }
        handle(event)

        # Should NOT create a staging file (output too short)
        staging_files = list((tmp_path / "staging").glob("bash_*.md"))
        assert len(staging_files) == 0


class TestPostToolUseGrep:
    """Test the Grep tool hook handler."""

    def test_handle_grep_creates_staging_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.post_tool_use import handle

        event = {
            "session_id": "test-session-4",
            "tool_name": "Grep",
            "tool_input": {"pattern": "def.*search", "path": "src/"},
            "tool_response": "src/search/hybrid.py:45:def hybrid_search(query_embedding, query_text, top_k):\nsrc/search/semantic.py:12:def semantic_search(embedding, top_k):\n",
        }
        handle(event)

        staging_files = list((tmp_path / "staging").glob("grep_*.md"))
        assert len(staging_files) == 1

        content = staging_files[0].read_text(encoding="utf-8")
        assert "Code Search: `def.*search`" in content
        assert "hybrid_search" in content

    def test_handle_grep_skips_short_output(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.post_tool_use import handle

        event = {
            "session_id": "s5",
            "tool_name": "Grep",
            "tool_input": {"pattern": "xyz_not_found", "path": "src/"},
            "tool_response": "",
        }
        handle(event)

        staging_files = list((tmp_path / "staging").glob("grep_*.md"))
        assert len(staging_files) == 0


# =========================================================================
# T-H3: UserPromptSubmit handler
# =========================================================================


class TestUserPrompt:
    """Test the UserPromptSubmit hook handler."""

    def test_handle_prompt_creates_staging_file(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.user_prompt import handle

        event = {
            "session_id": "test-session-6",
            "prompt": "Refactor the authentication module to use OAuth2",
        }
        handle(event)

        staging_files = list((tmp_path / "staging").glob("prompt_*.md"))
        assert len(staging_files) == 1

        content = staging_files[0].read_text(encoding="utf-8")
        assert "User Prompt" in content
        assert "Refactor the authentication module to use OAuth2" in content
        assert "user_intent" in content
        assert "test-session-6" in content

        queue = HookQueue(tmp_path / "hook_queue.db")
        assert queue.pending_count() == 1
        item = queue.dequeue()
        assert item.event_type == "user_prompt"
        queue.close()

    def test_handle_empty_prompt_ignored(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.user_prompt import handle

        handle({"session_id": "s7", "prompt": ""})
        handle({"session_id": "s7", "prompt": "   "})

        staging_files = list((tmp_path / "staging").glob("prompt_*.md"))
        assert len(staging_files) == 0


# =========================================================================
# T-H4: Session end handler
# =========================================================================


class TestSessionEnd:
    """Test the Stop hook handler."""

    def test_handle_with_summary(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        # Create a fake transcript and summary
        project_dir = tmp_path / "projects" / "test-project"
        session_id = "abc123"
        transcript_path = project_dir / f"{session_id}.jsonl"
        summary_dir = project_dir / session_id / "session-memory"
        summary_dir.mkdir(parents=True)
        transcript_path.write_text("{}", encoding="utf-8")
        summary_path = summary_dir / "summary.md"
        summary_path.write_text("# Session Summary\nBuilt the auth module.", encoding="utf-8")

        from claude_rag.hooks.session_end import handle

        event = {
            "session_id": session_id,
            "transcript_path": str(transcript_path),
            "stop_hook_active": False,
        }
        handle(event)

        queue = HookQueue(tmp_path / "hook_queue.db")
        assert queue.pending_count() == 1
        item = queue.dequeue()
        assert item.event_type == "session_end"
        assert item.staging_path == str(summary_path)
        queue.close()

    def test_handle_stop_hook_active_noop(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.session_end import handle

        handle({
            "session_id": "s1",
            "stop_hook_active": True,
        })

        queue = HookQueue(tmp_path / "hook_queue.db")
        assert queue.pending_count() == 0
        queue.close()


# =========================================================================
# T-H5: Worker tests
# =========================================================================


class TestHookWorker:
    """Test the background hook worker."""

    def test_drain_processes_all_items(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        # Create staging files
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()

        for i in range(3):
            f = staging_dir / f"test_{i}.md"
            f.write_text(
                f"# Test File {i}\n\n## Content\nSome test content for item {i}.\n",
                encoding="utf-8",
            )

        # Enqueue them
        queue = HookQueue(tmp_path / "hook_queue.db")
        for i in range(3):
            queue.enqueue(
                "read",
                {"file": f"test_{i}.py"},
                session_id="s1",
                staging_path=str(staging_dir / f"test_{i}.md"),
            )
        assert queue.pending_count() == 3
        queue.close()

        # Run worker
        from claude_rag.hooks.worker import HookWorker

        worker = HookWorker(queue=HookQueue(tmp_path / "hook_queue.db"))
        count = worker.drain()
        assert count == 3

        # All items should be done
        stats = worker.queue.stats()
        assert stats.get("done") == 3
        assert stats.get("pending", 0) == 0

    def test_process_one_returns_false_when_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        from claude_rag.hooks.worker import HookWorker

        worker = HookWorker(queue=HookQueue(tmp_path / "hook_queue.db"))
        assert worker.process_one() is False

    def test_missing_staging_file_fails_gracefully(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("claude_rag.config.Config.STATE_DIR", tmp_path)

        queue = HookQueue(tmp_path / "hook_queue.db")
        queue.enqueue(
            "read",
            {"file": "ghost.py"},
            staging_path=str(tmp_path / "staging" / "nonexistent.md"),
        )
        queue.close()

        from claude_rag.hooks.worker import HookWorker

        worker = HookWorker(queue=HookQueue(tmp_path / "hook_queue.db"))
        worker.process_one()

        # Should be marked as done (not error) since missing file is handled
        stats = worker.queue.stats()
        assert stats.get("done") == 1
