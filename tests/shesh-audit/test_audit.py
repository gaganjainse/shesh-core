"""Offline tests for the audit log and policy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_audit.log import AuditLog  # noqa: E402
from shesh_audit.policy import Policy, Rule, Verdict, default_policy  # noqa: E402
from shesh_audit.server import add_rule, check, record_execution, verify_integrity  # noqa: E402


@pytest.fixture()
def audit(tmp_path, monkeypatch):
    import shesh_audit.server as srv
    srv._log = AuditLog(root=tmp_path)
    return srv._log


def test_append_only_chain(audit):
    e1 = audit.record("coder", "write_file", "executed", args={"path": "/x"})
    e2 = audit.record("coder", "write_file", "executed", args={"path": "/y"})
    assert e1.prev_hash == ""
    assert e2.prev_hash == e1.hash
    assert e2.hash != e1.hash


def test_verify_detects_tampering(audit):
    audit.record("a", "t", "executed")
    audit.record("a", "t", "executed")
    ok, _ = audit.verify()
    assert ok
    # Tamper with the file
    lines = audit.path.read_text().splitlines()
    import json
    obj = json.loads(lines[-1])
    obj["result"] = "tampered"
    lines[-1] = json.dumps(obj)
    audit.path.write_text("\n".join(lines) + "\n")
    ok, bad = audit.verify()
    assert not ok and bad == 2


def test_default_policy_allows_reads():
    p = default_policy()
    assert p.decide("list_roles", {})[0] == Verdict.ALLOW
    assert p.decide("get_system_status", {})[0] == Verdict.ALLOW


def test_default_policy_denies_protected_paths():
    p = default_policy()
    v, _ = p.decide("write_file", {"path": "/home/u/.ssh/id_rsa"})
    assert v == Verdict.DENY


def test_default_policy_denies_protected_path_reads():
    p = default_policy()
    for tool in ("get_file", "list_files", "search_notes"):
        v, _ = p.decide(tool, {"path": "/home/u/.ssh/id_rsa"})
        assert v == Verdict.DENY


def test_default_policy_confirms_unknown():
    p = default_policy()
    v, _ = p.decide("something_weird", {})
    assert v == Verdict.CONFIRM


def test_custom_rule_precedence():
    p = Policy(rules=[Rule(Verdict.ALLOW, "safe_tool")])
    assert p.decide("safe_tool")[0] == Verdict.ALLOW


def test_server_check_logs_decision(audit):
    r = check("coder", "write_file", {"path": "/home/u/Documents/x.txt"})
    assert r["verdict"] in {"allow", "confirm", "deny"}
    assert "event_hash" in r


def test_server_blocks_secrets(audit):
    r = check("coder", "write_file", {"path": "/home/u/.ssh/key"})
    assert r["verdict"] == "deny"
    assert not r["allowed"]


def test_record_execution(audit):
    r = record_execution("coder", "run_tests", True, result="ok")
    assert r["ok"]
    assert len(audit.recent()) >= 1


def test_verify_integrity(audit):
    record_execution("coder", "x", True)
    assert verify_integrity()["ok"] is True


def test_add_rule(audit):
    add_rule("deny", "dangerous_tool", reason="no")
    r = check("coder", "dangerous_tool")
    assert r["verdict"] == "deny"


# ── reusable gate ──────────────────────────────────────────────
def test_guard_allows_reads():
    from shesh_audit.gate import Guard
    g = Guard()
    d = g.check("list_roles")
    assert d.allowed and not d.requires_confirmation


def test_guard_denies_secrets():
    from shesh_audit.gate import Guard
    g = Guard()
    d = g.check("write_file", {"path": "/home/u/.ssh/id_rsa"})
    assert not d.allowed and d.verdict == "deny"


def test_guard_requires_confirmation_for_writes():
    from shesh_audit.gate import Guard
    g = Guard()
    d = g.check("set_power_profile", {"profile": "performance"})
    assert d.requires_confirmation


def test_guard_logs_execution(tmp_path):
    from shesh_audit.gate import Guard
    from shesh_audit.log import AuditLog
    g = Guard(audit=AuditLog(root=tmp_path))
    g.log_execution("run_tests", True, result="ok")
    assert any(e["action"] == "run_tests" for e in g.audit.recent())


# ── SheshAOS event bridge ──────────────────────────────────────
def test_kernel_bridge_appends_events(tmp_path):
    from shesh_audit.kernel_bridge import KernelBridge, KernelEventKind
    bridge = KernelBridge(tmp_path / "kernel.jsonl")
    e1 = bridge.emit(KernelEventKind.TOOL_REQUESTED, {"tool": "x"})
    e2 = bridge.emit(KernelEventKind.TOOL_COMPLETED, {"ok": True})
    assert e1.sequence == 1 and e2.sequence == 2
    assert len(bridge.read()) == 2
    assert bridge.read()[0].kind == "ToolRequested"


def test_guard_emits_kernel_events(tmp_path):
    from shesh_audit.gate import Guard
    from shesh_audit.kernel_bridge import KernelBridge, KernelEventKind
    from shesh_audit.log import AuditLog
    bridge = KernelBridge(tmp_path / "kernel.jsonl")
    g = Guard(audit=AuditLog(root=tmp_path), bridge=bridge)
    g.check("list_roles")                      # allowed
    g.log_execution("list_roles", True)
    kinds = [e.kind for e in bridge.read()]
    assert KernelEventKind.TOOL_REQUESTED.value in kinds
    assert KernelEventKind.TOOL_COMPLETED.value in kinds


def test_guard_denied_emits_policy_denied(tmp_path):
    from shesh_audit.gate import Guard
    from shesh_audit.kernel_bridge import KernelBridge, KernelEventKind
    from shesh_audit.log import AuditLog
    bridge = KernelBridge(tmp_path / "kernel.jsonl")
    g = Guard(audit=AuditLog(root=tmp_path), bridge=bridge)
    g.check("write_file", {"path": "/home/u/.ssh/key"})  # denied
    assert any(e.kind == KernelEventKind.POLICY_DENIED.value for e in bridge.read())


# ── MCP GuardedMCP middleware ────────────────────────────────
def test_guarded_mcp_allows_read_tools(tmp_path):
    import asyncio

    from shesh_audit.gate import Guard
    from shesh_audit.log import AuditLog
    from shesh_audit.mcp_guard import GuardedMCP
    mcp = GuardedMCP("test", guard=Guard(audit=AuditLog(root=tmp_path)))

    @mcp.tool()
    def list_things() -> dict:
        return {"ok": True, "things": [1, 2, 3]}

    async def run_tool():
        tool = await mcp.get_tool("list_things")
        return await tool.run({})
    result = asyncio.run(run_tool())
    assert "[1, 2, 3]" in str(result)


def test_guarded_mcp_denies_secrets(tmp_path):
    import asyncio

    from shesh_audit.gate import Guard
    from shesh_audit.log import AuditLog
    from shesh_audit.mcp_guard import GuardedMCP
    from shesh_audit.policy import Policy, Rule, Verdict
    mcp = GuardedMCP("test", guard=Guard(audit=AuditLog(root=tmp_path)))
    mcp.guard = Guard(policy=Policy(rules=[Rule(Verdict.DENY, "*", path_glob="*/.ssh/*")]))

    @mcp.tool()
    def write_file(path: str) -> dict:
        return {"ok": True, "wrote": path}

    async def run_tool():
        tool = await mcp.get_tool("write_file")
        return await tool.run({"path": "/home/u/.ssh/id_rsa"})
    result = asyncio.run(run_tool())
    assert "denied" in str(result)


def test_guarded_mcp_does_not_execute_confirmation(tmp_path):
    import asyncio

    from shesh_audit.gate import Guard
    from shesh_audit.log import AuditLog
    from shesh_audit.mcp_guard import GuardedMCP
    called = False
    mcp = GuardedMCP("test", guard=Guard(audit=AuditLog(root=tmp_path)))

    @mcp.tool()
    def write_thing() -> dict:
        nonlocal called
        called = True
        return {"ok": True}

    async def run_tool():
        tool = await mcp.get_tool("write_thing")
        return await tool.run({})

    result = asyncio.run(run_tool())
    assert "confirmation required" in str(result)
    assert called is False


def test_load_policy_configurable_default(tmp_path):
    from shesh_audit.policy import load_policy
    p = tmp_path / "policy.json"
    p.write_text('{"default_verdict": "deny", "protected_paths": false}')
    pol = load_policy(p)
    v, _ = pol.decide("some_unmatched_tool")
    assert v.value == "deny"
    # protected path no longer hard-denied -> falls through to default deny anyway
    v2, _ = pol.decide("write_file", {"path": "/home/u/.ssh/config"})
    assert v2.value == "deny"


def test_load_policy_protected_paths_on(tmp_path):
    from shesh_audit.policy import load_policy
    p = tmp_path / "policy.json"
    p.write_text('{"default_verdict": "allow", "protected_paths": true}')
    pol = load_policy(p)
    v, _ = pol.decide("write_file", {"path": "/home/u/.ssh/config"})
    assert v.value == "deny"
    v2, _ = pol.decide("something_else")
    assert v2.value == "allow"


def test_load_policy_missing_file_falls_back_to_defaults(tmp_path):
    from shesh_audit.policy import Verdict, load_policy
    pol = load_policy(tmp_path / "does-not-exist.json")
    v, _ = pol.decide("totally_unknown_tool")
    assert v == Verdict.CONFIRM


def test_load_policy_corrupt_file_falls_back(tmp_path):
    from shesh_audit.policy import Verdict, load_policy
    p = tmp_path / "policy.json"
    p.write_text("{not json!")
    pol = load_policy(p)
    v, _ = pol.decide("totally_unknown_tool")
    assert v == Verdict.CONFIRM


def test_save_policy_roundtrip(tmp_path):
    from shesh_audit.policy import Verdict, load_policy, save_policy
    p = save_policy("deny", False, path=tmp_path / "policy.json")
    pol = load_policy(p)
    v, _ = pol.decide("unmatched")
    assert v == Verdict.DENY
