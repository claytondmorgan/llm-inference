"""Metadata extractor for the Claude Code RAG system.

Enriches parsed blocks and chunks with extracted metadata such as
referenced file paths, programming language, content intent, and
project name.  The main entry point is :func:`enrich_chunk_metadata`.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-extension whitelist used by the path extractor
# ---------------------------------------------------------------------------

_FILE_EXTENSIONS = (
    r"\.(?:py|js|ts|tsx|java|go|rs|sql|md|json|yaml|yml|toml|cfg|env"
    r"|sh|bash|css|html|xml)"
)

# ---------------------------------------------------------------------------
# File-reference patterns
# ---------------------------------------------------------------------------

# Quoted paths: "path/to/file.py" or 'src/index.js'
_QUOTED_PATH_RE = re.compile(
    rf"""(?:"|')                      # opening quote
    (?P<path>                         # capture the path
        (?:[A-Za-z]:)?               # optional drive letter (Windows)
        [\w./\\\-]+                  # path body (word chars, separators)
        {_FILE_EXTENSIONS}           # must end with a known extension
    )
    (?:"|')                          # closing quote
    """,
    re.VERBOSE,
)

# Windows absolute paths: C:\Users\...\file.py
_WIN_ABS_PATH_RE = re.compile(
    rf"""(?<!\w)                      # not preceded by a word character
    (?P<path>
        [A-Za-z]:\\                   # drive letter + backslash
        [\w\\.\-]+                   # path body with backslashes
        {_FILE_EXTENSIONS}           # known extension
    )
    (?!\w)                           # not followed by a word character
    """,
    re.VERBOSE,
)

# Windows relative paths: .\src\main.py or ..\dir\file.py
_WIN_REL_PATH_RE = re.compile(
    rf"""(?<!\w)                      # not preceded by a word character
    (?P<path>
        \.{{1,2}}\\                  # .\ or ..\
        [\w\\.\-]+                   # path body with backslashes
        {_FILE_EXTENSIONS}           # known extension
    )
    (?!\w)                           # not followed by a word character
    """,
    re.VERBOSE,
)

# Unix / POSIX paths: src/auth.py, ./config/db.yaml, /usr/local/bin/python.sh
# Also covers relative paths like ../some/file.py
_UNIX_PATH_RE = re.compile(
    rf"""(?<!\w)                      # not preceded by a word character
    (?P<path>
        (?:\.{{0,2}}/)?              # optional ./ or ../ or /
        [\w./\-]+                    # path body (forward slashes)
        {_FILE_EXTENSIONS}           # known extension
    )
    (?!\w)                           # not followed by a word character
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Language alias normalization map
# ---------------------------------------------------------------------------

_LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "python": "python",
    "python3": "python",
    "js": "javascript",
    "javascript": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "tsx": "typescript",
    "go": "go",
    "golang": "go",
    "rs": "rust",
    "rust": "rust",
    "java": "java",
    "sql": "sql",
    "sh": "shell",
    "bash": "shell",
    "shell": "shell",
    "zsh": "shell",
    "css": "css",
    "html": "html",
    "xml": "xml",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "md": "markdown",
    "markdown": "markdown",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "rb": "ruby",
    "ruby": "ruby",
}

# ---------------------------------------------------------------------------
# Language-detection heuristics (applied in order)
# ---------------------------------------------------------------------------

_LANG_HEURISTICS: list[tuple[str, re.Pattern[str]]] = [
    ("python", re.compile(r"\bdef\s+\w+\s*\(", re.MULTILINE)),
    ("python", re.compile(r"\bimport\s+\w+.*\bfrom\s+", re.MULTILINE | re.DOTALL)),
    ("javascript", re.compile(r"\bfunction\s+\w+\s*\(", re.MULTILINE)),
    ("javascript", re.compile(r"\bconst\s+\w+\s*=", re.MULTILINE)),
    ("javascript", re.compile(r"=>")),
    ("go", re.compile(r"\bfunc\s+\w+", re.MULTILINE)),
    ("go", re.compile(r"\bpackage\s+\w+", re.MULTILINE)),
    ("rust", re.compile(r"\bfn\s+\w+", re.MULTILINE)),
    ("rust", re.compile(r"\blet\s+mut\b", re.MULTILINE)),
    ("sql", re.compile(r"\bSELECT\s+", re.MULTILINE | re.IGNORECASE)),
    ("sql", re.compile(r"\bCREATE\s+TABLE\b", re.MULTILINE | re.IGNORECASE)),
    ("java", re.compile(r"\bclass\s+\w+.*\b(?:public|private)\b", re.MULTILINE | re.DOTALL)),
    ("java", re.compile(r"\b(?:public|private)\b.*\bclass\s+\w+", re.MULTILINE)),
]

# ---------------------------------------------------------------------------
# Intent classification rules (priority order)
# ---------------------------------------------------------------------------

_INTENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "bug-fix",
        re.compile(
            r"\b(?:fix(?:e[ds])?|bug(?:s)?|error(?:s)?|issue(?:s)?|patch(?:e[ds])?|resolv(?:e[ds]?|ing))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "refactor",
        re.compile(
            r"\b(?:refactor(?:ed|ing|s)?|renam(?:e[ds]?|ing)|restructur(?:e[ds]?|ing)|reorganiz(?:e[ds]?|ing)|cleanup)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "new-feature",
        re.compile(
            r"\b(?:add(?:ed|ing|s)?|creat(?:e[ds]?|ing)|implement(?:ed|ing|s)?|build(?:ing|s)?|new)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "investigation",
        re.compile(
            r"\b(?:investigat(?:e[ds]?|ing)|debug(?:ging|ged|s)?|explor(?:e[ds]?|ing)|understand(?:ing)?|research(?:ed|ing)?|study(?:ing)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "configuration",
        re.compile(
            r"\b(?:config(?:uration|ure)?|setup|install(?:ation)?|deploy(?:ment)?|environment|settings)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "documentation",
        re.compile(
            r"\b(?:docs?|documentation|readme|comment|explain|describe)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "testing",
        re.compile(
            r"\b(?:test(?:ed|ing|s)?|assert(?:ion|s|ed|ing)?|mock(?:ed|ing|s)?|fixture(?:s)?|pytest)\b",
            re.IGNORECASE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_file_references(content: str) -> list[str]:
    """Extract file paths referenced in *content*.

    Recognises Unix paths, Windows absolute and relative paths, and
    quoted paths that end with a known file extension.

    Args:
        content: Arbitrary text that may contain embedded file paths.

    Returns:
        Deduplicated list of file-path strings found in *content*,
        preserving the order of first occurrence.
    """
    seen: set[str] = set()
    results: list[str] = []

    # Apply patterns in specificity order: quoted first, then Windows,
    # then Unix (most general).
    for pattern in (
        _QUOTED_PATH_RE,
        _WIN_ABS_PATH_RE,
        _WIN_REL_PATH_RE,
        _UNIX_PATH_RE,
    ):
        for match in pattern.finditer(content):
            path = match.group("path")
            if path not in seen:
                seen.add(path)
                results.append(path)

    if results:
        logger.debug("Extracted %d file reference(s) from content", len(results))

    return results


def detect_language(
    content: str,
    code_fence_lang: str | None = None,
) -> str | None:
    """Detect the programming language of *content*.

    If *code_fence_lang* is provided (e.g. from a fenced code block's
    info string), it is normalised and returned directly.  Otherwise
    simple heuristics on *content* are used to guess the language.

    Args:
        content: The source text to analyse.
        code_fence_lang: Optional language hint from a markdown code
            fence (e.g. ``"py"``, ``"typescript"``).

    Returns:
        Normalised language name, or ``None`` if detection fails.
    """
    # Prefer explicit fence language when available.
    if code_fence_lang:
        normalised = _LANG_ALIASES.get(code_fence_lang.lower().strip())
        if normalised:
            return normalised
        # Return the raw hint lower-cased if we have no alias for it.
        return code_fence_lang.lower().strip()

    # Fall back to content-based heuristics.
    for lang, pattern in _LANG_HEURISTICS:
        if pattern.search(content):
            return lang

    return None


def classify_intent(content: str) -> str:
    """Classify the intent or purpose of *content*.

    Uses word-boundary regex matching against a priority-ordered set
    of keyword groups.

    Args:
        content: The text whose intent should be classified.

    Returns:
        One of ``"bug-fix"``, ``"refactor"``, ``"new-feature"``,
        ``"investigation"``, ``"configuration"``, ``"documentation"``,
        ``"testing"``, or ``"general"`` (fallback).
    """
    for intent, pattern in _INTENT_RULES:
        if pattern.search(content):
            return intent

    return "general"


def extract_project_name(file_path: str) -> str | None:
    """Derive a project name from *file_path*.

    Heuristics (applied in order):

    1. If the path contains a ``src/`` segment, return the directory
       name immediately preceding ``src/``.
    2. Otherwise, look for common project-root markers by walking up
       the path components and returning the deepest directory name
       that is not a well-known generic directory (``Users``, ``home``,
       ``projects``, etc.).

    Args:
        file_path: Absolute or relative file path.

    Returns:
        Project name string, or ``None`` if it cannot be determined.
    """
    # Normalise to forward slashes for uniform handling.
    normalised = file_path.replace("\\", "/")
    parts = [p for p in normalised.split("/") if p]

    if not parts:
        return None

    # Strategy 1: directory immediately before "src/"
    for i, part in enumerate(parts):
        if part == "src" and i > 0:
            return parts[i - 1]

    # Strategy 2: walk backwards, skip the filename itself and
    # well-known generic directory names.
    _GENERIC_DIRS = {
        "users",
        "home",
        "projects",
        "documents",
        "desktop",
        "repos",
        "repositories",
        "workspace",
        "workspaces",
        "var",
        "tmp",
        "opt",
        "usr",
        "local",
        "bin",
        "lib",
    }

    # Drop filename (last component) — only consider directories.
    dir_parts = parts[:-1] if len(parts) > 1 else parts

    for part in reversed(dir_parts):
        # Skip drive letters like "C:"
        if len(part) <= 2 and part.endswith(":"):
            continue
        if part.lower() not in _GENERIC_DIRS:
            return part

    return None


def enrich_chunk_metadata(
    content: str,
    block_type: str | None,
    source_path: str | None,
    existing_metadata: dict | None = None,
) -> dict:
    """Build an enriched metadata dictionary for a chunk.

    Calls all individual extractors and merges the results with any
    *existing_metadata*.  Keys with ``None`` or empty values are
    omitted from the output.

    Args:
        content: The chunk text content.
        block_type: Semantic block type (e.g. ``"code"``, ``"text"``),
            or ``None`` if unknown.
        source_path: File path the content was parsed from, used for
            project-name extraction.  May be ``None``.
        existing_metadata: Optional pre-existing metadata dict whose
            keys will be preserved in the output.

    Returns:
        Merged metadata dictionary with extracted fields.
    """
    metadata: dict = dict(existing_metadata) if existing_metadata else {}

    # File references
    files = extract_file_references(content)
    if files:
        metadata["files"] = files

    # Language detection — use code_fence_lang from existing metadata
    # if available (set by the parser for code blocks).
    code_fence_lang = metadata.get("language") if block_type == "code" else None
    language = detect_language(content, code_fence_lang=code_fence_lang)
    if language:
        metadata["language"] = language

    # Intent classification
    intent = classify_intent(content)
    if intent != "general":
        metadata["intent"] = intent

    # Project name
    if source_path:
        project = extract_project_name(source_path)
        if project:
            metadata["project"] = project

    return metadata
