"""Hook-based real-time interception for the Claude Code RAG system.

Provides PostToolUse, UserPromptSubmit, and Stop hooks that capture
Claude Code events and enqueue them for async ingestion into the RAG
pipeline.
"""
