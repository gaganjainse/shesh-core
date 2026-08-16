"""MCP server — packaged Shesh kernel for desktop: policy routing + kernel event bridge.

Task/session management is owned by the shesh-orchestrator MCP server
(execute / start_session / get_session / list_sessions / cancel_session);
brain deliberately does not duplicate it.
"""

from __future__ import annotations

from shesh_audit.gate import Guard
from shesh_audit.kernel_bridge import KernelBridge, KernelEventKind
from shesh_audit.mcp_guard import GuardedMCP as FastMCP

mcp = FastMCP("shesh-brain")

# Lazily build the kernel bridge + guard so importing this module is cheap and
# does not fail (or read the whole audit log) when the kernel event store is not
# yet available. Constructed once, on first tool call.
_guard: Guard | None = None


def guard() -> Guard:
    global _guard
    if _guard is None:
        _guard = Guard(bridge=KernelBridge())
    return _guard


@mcp.tool()
def route_tool_call(actor: str, tool: str, args: dict | None = None) -> dict:
    """Check a proposed tool call against Shesh policy and record the decision.

    The Guard audit-logs every decision and mirrors it to the kernel event
    store. The caller executes the tool only when this returns allowed=True
    (or after human confirmation when requires_confirmation=True).
    """
    args = args or {}
    decision = guard().check(tool, args, actor=actor)
    return {
        "allowed": decision.allowed,
        "requires_confirmation": decision.requires_confirmation,
        "verdict": decision.verdict,
        "reason": decision.reason,
    }


@mcp.tool()
def get_policy() -> dict:
    """Return a view of the active policy (rule count and rules)."""
    try:
        rules = [
            {"tool": r.tool, "verdict": r.verdict.value, "reason": r.reason}
            for r in guard().policy.rules
        ]
        return {"guard": True, "rule_count": len(rules), "rules": rules}
    except Exception as e:  # noqa: BLE001 — MCP tool boundary returns error dicts
        return {"guard": True, "error": str(e)}


@mcp.tool()
def record_confirmation(actor: str, tool: str, approved: bool, reason: str = "") -> dict:
    """Resolve a confirmation that route_tool_call asked for.

    route_tool_call answering requires_confirmation=True starts a two-phase
    flow; this tool is the second phase. The resolution is audit-recorded and
    mirrored to the kernel event store like every other decision — a
    confirmation that leaves no trail would defeat the audit design.
    """
    kind = KernelEventKind.CONFIRMATION_GRANTED if approved else KernelEventKind.CONFIRMATION_DENIED
    guard().audit.record(
        actor, tool,
        "confirmation-granted" if approved else "confirmation-denied",
        args={}, result=reason,
    )
    guard().bridge.emit(kind, {"actor": actor, "tool": tool, "reason": reason})
    return {
        "ok": True,
        "verdict": kind.name.lower().replace("_", "-"),
        "actor": actor,
        "tool": tool,
        "may_execute": approved,
    }


@mcp.tool()
def audit_tail(limit: int = 20) -> dict:
    """Return the newest audit events (decisions, confirmations, executions).

    The audit log is an append-only hash-chained ledger (see shesh-audit);
    audit.recent() reads it without mutation. Verify chain integrity with
    shesh-audit's own verify() — brain only serves the read view here.
    """
    limit = max(1, min(int(limit), 500))
    events = guard().audit.recent(limit)
    return {"ok": True, "count": len(events), "events": events}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
