"""Tests for the metadata extractor module."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claude_rag.ingestion.metadata import (
    classify_intent,
    detect_language,
    enrich_chunk_metadata,
    extract_file_references,
    extract_project_name,
)


class TestExtractFileReferences:
    """Tests for extract_file_references."""

    def test_unix_paths(self) -> None:
        content = "Look at src/auth.py and config/db.yaml for details."
        refs = extract_file_references(content)
        assert "src/auth.py" in refs
        assert "config/db.yaml" in refs

    def test_relative_paths(self) -> None:
        content = "Wraps ../lambda-s3-trigger/ingestion-worker/app/embeddings.py"
        refs = extract_file_references(content)
        assert any("embeddings.py" in r for r in refs)

    def test_windows_paths(self) -> None:
        content = r"File is at C:\Users\Clay\project\main.py"
        refs = extract_file_references(content)
        assert any("main.py" in r for r in refs)

    def test_quoted_paths(self) -> None:
        content = 'Check "tests/test_search.py" for examples.'
        refs = extract_file_references(content)
        assert "tests/test_search.py" in refs

    def test_no_paths(self) -> None:
        content = "This text has no file paths at all."
        refs = extract_file_references(content)
        assert refs == []

    def test_deduplication(self) -> None:
        content = "src/main.py and src/main.py again"
        refs = extract_file_references(content)
        assert refs.count("src/main.py") == 1


class TestDetectLanguage:
    """Tests for detect_language."""

    def test_code_fence_hint(self) -> None:
        assert detect_language("anything", code_fence_lang="py") == "python"
        assert detect_language("anything", code_fence_lang="ts") == "typescript"
        assert detect_language("anything", code_fence_lang="golang") == "go"

    def test_python_heuristic(self) -> None:
        assert detect_language("def hello():\n    pass") == "python"

    def test_javascript_heuristic(self) -> None:
        assert detect_language("const x = () => 42") == "javascript"

    def test_go_heuristic(self) -> None:
        assert detect_language("func main() {\n}") == "go"

    def test_rust_heuristic(self) -> None:
        assert detect_language("fn main() {\n    let mut x = 5;\n}") == "rust"

    def test_sql_heuristic(self) -> None:
        assert detect_language("SELECT * FROM users WHERE id = 1") == "sql"

    def test_no_language(self) -> None:
        assert detect_language("Just plain text with no code.") is None


class TestClassifyIntent:
    """Tests for classify_intent."""

    def test_bug_fix(self) -> None:
        assert classify_intent("Fixed the failing test") == "bug-fix"
        assert classify_intent("Resolved the login error") == "bug-fix"

    def test_refactor(self) -> None:
        assert classify_intent("Refactored the database module") == "refactor"

    def test_new_feature(self) -> None:
        assert classify_intent("Added hybrid search support") == "new-feature"

    def test_investigation(self) -> None:
        assert classify_intent("Investigating memory leak") == "investigation"

    def test_configuration(self) -> None:
        assert classify_intent("Updated the deployment settings") == "configuration"

    def test_documentation(self) -> None:
        assert classify_intent("Updated the README docs") == "documentation"

    def test_testing(self) -> None:
        assert classify_intent("Run the pytest fixtures to verify") == "testing"

    def test_general_fallback(self) -> None:
        assert classify_intent("Hello world") == "general"

    def test_word_boundary(self) -> None:
        # "suffix" should NOT match "fix"
        assert classify_intent("The suffix of the string") == "general"


class TestExtractProjectName:
    """Tests for extract_project_name."""

    def test_with_src_dir(self) -> None:
        assert extract_project_name("/home/user/my-app/src/main.py") == "my-app"

    def test_windows_path(self) -> None:
        result = extract_project_name(
            r"C:\Users\Clay\PycharmProjects\llm-inference\app.py"
        )
        assert result == "llm-inference"

    def test_no_project(self) -> None:
        result = extract_project_name("file.py")
        # Single file with no directory context
        assert result is None or isinstance(result, str)


class TestEnrichChunkMetadata:
    """Tests for enrich_chunk_metadata."""

    def test_enriches_code_block(self) -> None:
        content = "def hello():\n    return 'world'"
        meta = enrich_chunk_metadata(
            content=content,
            block_type="code",
            source_path="/home/user/my-app/src/main.py",
            existing_metadata={"language": "py"},
        )
        assert meta["language"] == "python"  # normalized from "py"
        assert meta["project"] == "my-app"

    def test_enriches_text_block(self) -> None:
        content = "Fixed the bug in src/auth.py that caused login failures."
        meta = enrich_chunk_metadata(
            content=content,
            block_type="text",
            source_path="/projects/my-app/CLAUDE.md",
        )
        assert "src/auth.py" in meta.get("files", [])
        assert meta.get("intent") == "bug-fix"

    def test_preserves_existing_metadata(self) -> None:
        meta = enrich_chunk_metadata(
            content="Hello",
            block_type="text",
            source_path=None,
            existing_metadata={"token_count": 42, "block_types": ["text"]},
        )
        assert meta["token_count"] == 42
        assert meta["block_types"] == ["text"]

    def test_no_intent_for_general(self) -> None:
        meta = enrich_chunk_metadata(
            content="Hello world",
            block_type="text",
            source_path=None,
        )
        # "general" intent should not be stored
        assert "intent" not in meta
