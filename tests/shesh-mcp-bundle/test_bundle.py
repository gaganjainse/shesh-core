"""Tests for the MCP bundle: mount wiring, namespacing, guard middleware."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402
from fastmcp import Client, FastMCP  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from shesh_mcp_bundle import server as bundle_server  # noqa: E402
from shesh_mcp_bundle.registry import (  # noqa: E402
    BundledServer,
    default_servers,
)


def _upstream(name="up") -> FastMCP:
    """An in-memory 'upstream' MCP server with one tool."""
    up = FastMCP(name)

    @up.tool()
    def read_file(path: str) -> dict:
        return {"ok": True, "path": path}

    return up


def _fresh_guarded(name="test-bundle"):
    """GuardedMCP independent of module-level singleton."""
    import tempfile

    from shesh_audit.gate import Guard
    from shesh_audit.log import AuditLog
    from shesh_audit.mcp_guard import GuardedMCP
    from shesh_audit.policy import Policy, Rule, Verdict

    guard = Guard(
        audit=AuditLog(root=Path(tempfile.mkdtemp())),
        policy=Policy(rules=[Rule(Verdict.DENY, "*", path_glob="*/.ssh/*")]),
    )
    return GuardedMCP(name, guard=guard)


@pytest.mark.asyncio
async def test_mount_namespaces_tools():
    srv = _fresh_guarded()
    srv.mount(_upstream(), namespace="fs")
    async with Client(srv) as c:
        tools = await c.list_tools()
        assert any(t.name == "fs_read_file" for t in tools)


@pytest.mark.asyncio
async def test_proxied_call_runs_through_guard_allow():
    srv = _fresh_guarded()
    srv.mount(_upstream(), namespace="fs")
    async with Client(srv) as c:
        r = await c.call_tool("fs_read_file", {"path": "/tmp/ok.txt"})
        assert r.is_error is False


@pytest.mark.asyncio
async def test_proxied_call_denied_by_guard():
    srv = _fresh_guarded()
    srv.mount(_upstream(), namespace="fs")
    async with Client(srv) as c:
        with pytest.raises(ToolError, match="denied"):
            await c.call_tool("fs_read_file", {"path": "/home/u/.ssh/id_rsa"})


def test_stdio_config_shape():
    cfg = bundle_server._stdio_config(
        BundledServer("filesystem", ("npx", "-y", "srv", "/root"), "fs", "d")
    )
    entry = cfg["mcpServers"]["filesystem"]
    assert entry["command"] == "npx"
    assert entry["args"] == ["-y", "srv", "/root"]
    assert entry["transport"] == "stdio"


def test_mount_available_skips_missing(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda c: None)
    missing = BundledServer("nope", ("nonexistent-xyz",), "np", "d")
    assert bundle_server.mount_available([missing]) == []


def test_mount_available_required_raises(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda c: None)
    required = BundledServer("req", ("nonexistent-xyz",), "rq", "d", required=True)
    with pytest.raises(RuntimeError, match="required MCP server"):
        bundle_server.mount_available([required])


def test_registry_defaults():
    servers = default_servers(home=Path("/tmp/fakehome"))
    names = {s.name for s in servers}
    assert {"filesystem", "fetch", "git"} <= names
