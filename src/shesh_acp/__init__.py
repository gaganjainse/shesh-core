"""shesh-acp: minimal Agent Client Protocol (ACP) server.

Implements enough of the ACP spec (Zed/JetBrains JSON-RPC over stdio) for Shesh
to run as an editor agent: initialize, sessions, prompt turns with streaming
updates, permission requests, and scoped file/terminal access. All side effects
go through a policy layer so the same governance applies as in other clients.

ACP is agent<->client (editor); MCP is agent<->tools. They stack.
"""
from __future__ import annotations

__version__ = "0.1.0"
