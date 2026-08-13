"""Shesh skills MCP server (stdio).

Exposes everyday tools: notes/vault, web search & fetch, git/github helpers,
document conversion, and reminders. Designed for local-first use.
"""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from . import tools

mcp = _MCP("shesh-skills")


@mcp.tool()
def append_note(name: str, content: str, timestamp: bool = True) -> dict:
    """Append text to a markdown note in your Notes vault (creates it if missing)."""
    return tools.append_note(name, content, timestamp=timestamp)


@mcp.tool()
def search_notes(query: str) -> list[dict]:
    """Full-text search across your Notes vault."""
    return tools.search_notes(query)


@mcp.tool()
def find_notes(query: str) -> list[str]:
    """Find note filenames matching a query."""
    return tools.find_notes(query)


@mcp.tool()
def web_search(query: str, limit: int = 5) -> list[dict]:
    """Search the web (DuckDuckGo, no API key required)."""
    return tools.duckduckgo_search(query, limit)


@mcp.tool()
def fetch_url(url: str) -> dict:
    """Fetch a URL and return its text content."""
    return tools.fetch_url(url)


@mcp.tool()
def git_status(path: str = ".") -> str:
    """Show git status for a repository path."""
    return tools.git_status(path)


@mcp.tool()
def git_log(path: str = ".", n: int = 10) -> str:
    """Show recent git commits."""
    return tools.git_log(path, n)


@mcp.tool()
def github_view(repo: str) -> dict:
    """View a GitHub repository's metadata (owner/repo)."""
    return tools.github_view(repo)


@mcp.tool()
def convert_to_markdown(file_path: str) -> str:
    """Convert a document file to Markdown via pandoc."""
    return tools.convert_to_markdown(file_path)


@mcp.tool()
def remind(in_minutes: int, text: str) -> dict:
    """Schedule a desktop reminder in N minutes."""
    return tools.remind(in_minutes, text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
