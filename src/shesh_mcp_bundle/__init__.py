"""shesh-mcp-bundle: curated third-party MCP servers behind the Guard.

Rather than re-implementing filesystem/git/fetch, this component runs the
upstream MCP servers as subprocesses and proxies their tool calls through
shesh-audit's policy gate. Each bundled server is declared with the command
used to launch it and the tool-name prefix it is exposed under.

Currently bundled (all optional and opt-in):
  - filesystem: @modelcontextprotocol/server-filesystem
  - fetch:      @modelcontextprotocol/server-fetch
  - git:        mcp-server-git

If a server's command is not installed, it is skipped with a warning rather
than crashing the bundle.
"""
from __future__ import annotations

__version__ = "0.1.0"
