"""MCP server exposing the RAG search tool for Claude Code.

Runs in stdio mode and exposes a single ``rag_search`` tool that performs
hybrid (semantic + keyword) search against the local pgvector-backed
memory database.

Usage:
    python -m claude_rag serve          # via the CLI entry-point
    python -m claude_rag.mcp_server.server  # direct invocation
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server with the ``rag_search`` tool.

    The server lazily initialises the configuration, database manager, and
    embedding provider on the first tool call so that import time stays fast
    and no external resources are touched until actually needed.

    Returns:
        A fully configured ``Server`` instance ready to be run.
    """
    server = Server("claude-rag")

    # Lazily initialised on first tool call.
    _config: object | None = None
    _db: object | None = None
    _embedder: object | None = None

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Advertise the rag_search tool to MCP clients."""
        return [
            Tool(
                name="rag_search",
                description=(
                    "Search local RAG database of Claude Code memories and "
                    "session history. Returns relevant context from past coding "
                    "sessions, project instructions, and architectural decisions. "
                    "ALWAYS call this first before reading files directly."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Natural language description of what context "
                                "you need"
                            ),
                        },
                        "token_budget": {
                            "type": "integer",
                            "description": (
                                "Max tokens for returned context (default: 4096)"
                            ),
                            "default": 4096,
                        },
                        "project_filter": {
                            "type": "string",
                            "description": "Filter to specific project path",
                        },
                        "block_type_filter": {
                            "type": "string",
                            "description": (
                                "Filter by block type: instruction, code, text, "
                                "heading"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle incoming tool calls.

        Args:
            name: The tool name requested by the client.
            arguments: The tool arguments provided by the client.

        Returns:
            A list containing a single ``TextContent`` with the formatted
            search results, or an error / empty-result message.
        """
        nonlocal _config, _db, _embedder

        if name != "rag_search":
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        # -- Lazy initialisation -----------------------------------------------
        if _config is None:
            from claude_rag.config import Config
            from claude_rag.db.manager import DatabaseManager
            from claude_rag.embeddings.local import LocalEmbeddingProvider

            _config = Config()
            _db = DatabaseManager(_config)
            _embedder = LocalEmbeddingProvider()
            logger.info("MCP server components initialised lazily")

        # -- Extract arguments -------------------------------------------------
        query: str = arguments["query"]
        token_budget: int = arguments.get(
            "token_budget", _config.CONTEXT_TOKEN_BUDGET
        )
        project_filter: str | None = arguments.get("project_filter")
        block_type_filter: str | None = arguments.get("block_type_filter")

        # -- Build filters -----------------------------------------------------
        from claude_rag.search.formatter import deduplicate_results, format_context
        from claude_rag.search.hybrid import build_filters, hybrid_search

        filter_clause, filter_params = build_filters(
            project_filter=project_filter,
            block_type_filter=block_type_filter,
        )

        # -- Embed the query ---------------------------------------------------
        query_embedding: list[float] = _embedder.embed_single(query)

        # -- Execute hybrid search ---------------------------------------------
        conn = _db._get_connection()
        try:
            results = hybrid_search(
                query_embedding=query_embedding,
                query_text=query,
                top_k=_config.SEARCH_TOP_K,
                db_conn=conn,
                rrf_k=_config.RRF_K,
                filter_clause=filter_clause,
                filter_params=filter_params,
            )
        finally:
            conn.close()

        # -- Post-process results ----------------------------------------------
        results = [
            r for r in results if r.similarity >= _config.RELEVANCE_THRESHOLD
        ]
        results = deduplicate_results(results)
        context: str = format_context(results, token_budget=token_budget)

        if not context.strip():
            context = (
                "(No relevant context found in RAG database for this query.)"
            )

        return [TextContent(type="text", text=context)]

    return server


async def main() -> None:
    """Run the MCP server in stdio mode.

    Blocks until the client disconnects or the process is interrupted.
    """
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
