"""Registry of curated third-party MCP servers.

Each entry knows how to launch its upstream server. We deliberately keep this
declarative: the actual subprocess proxying is in proxy.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundledServer:
    name: str
    # Command to launch the upstream server (argv).
    command: tuple[str, ...]
    # Prefix added to its tool names when exposed, e.g. "fs_read_file".
    prefix: str
    description: str
    # If true, missing command is a hard error rather than a skip.
    required: bool = False


def _npx(*args: str) -> tuple[str, ...]:
    return ("npx", "-y") + args


def _uvx(*args: str) -> tuple[str, ...]:
    return ("uvx",) + args


def default_servers(home: Path | None = None) -> list[BundledServer]:
    home = home or Path.home()
    docs = home / "Documents"
    return [
        BundledServer(
            name="filesystem",
            command=_npx("@modelcontextprotocol/server-filesystem", str(docs)),
            prefix="fs",
            description="Read/write files under an allowed root",
        ),
        BundledServer(
            name="fetch",
            command=_uvx("mcp-server-fetch"),
            prefix="fetch",
            description="Fetch and convert web pages to markdown",
        ),
        BundledServer(
            name="git",
            command=_uvx("mcp-server-git", "--repository", str(home / "code")),
            prefix="git",
            description="Inspect git repositories",
        ),
    ]


def is_available(cmd: str) -> bool:
    """Check whether a command exists on PATH."""
    import shutil
    return shutil.which(cmd) is not None
