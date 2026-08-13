"""MCP server exposing bundled third-party MCP servers behind the Guard.

FastMCP 3 mounts each available upstream via its stdio transport (native,
schema-correct, no hand-rolled JSON-RPC) under the registry's namespace
prefix. Guard enforcement rides GuardedMCP's protocol middleware, so proxied
calls are policy-checked exactly like locally registered tools.
"""
from __future__ import annotations

from fastmcp.server import create_proxy

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .registry import BundledServer, default_servers

mcp = _MCP("shesh-mcp-bundle")


def _stdio_config(server: BundledServer) -> dict:
    """MCPConfig entry for one stdio upstream (command + args)."""
    return {
        "mcpServers": {
            server.name: {
                "command": server.command[0],
                "args": list(server.command[1:]),
                "transport": "stdio",
            }
        }
    }


class ServerUnavailableError(RuntimeError):
    """A required MCP server binary is not on PATH."""

    def __init__(self, name: str, command: str) -> None:
        super().__init__(f"required MCP server {name!r}: {command} not on PATH")


def mount_available(servers: list[BundledServer] | None = None) -> list[str]:
    """Proxy-mount every available upstream under its namespace.

    Skips servers whose launcher binary is missing (unless required=True,
    which raises, as before). Returns the namespaces actually mounted.
    Connection to the upstream is lazy — established on first tool call.
    """
    import shutil

    mounted: list[str] = []
    for server in servers if servers is not None else default_servers():
        if shutil.which(server.command[0]) is None:
            if server.required:
                raise ServerUnavailableError(server.name, server.command[0])
            continue
        proxy = create_proxy(_stdio_config(server))
        mcp.mount(proxy, namespace=server.prefix)
        mounted.append(server.prefix)
    return mounted


mount_available()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
