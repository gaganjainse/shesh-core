"""MCP server exposing the audit log and policy gate."""
from __future__ import annotations

from fastmcp import FastMCP

from .log import AuditLog
from .policy import Verdict, load_policy

mcp = FastMCP("shesh-audit")

_log: AuditLog | None = None
_policy = load_policy()


def log() -> AuditLog:
    global _log
    if _log is None:
        _log = AuditLog()
    return _log


@mcp.tool()
def check(actor: str, tool: str, args: dict | None = None) -> dict:
    """Evaluate a proposed action against policy and log the decision."""
    verdict, reason = _policy.decide(tool, args)
    ev = log().record(actor, tool, verdict.value, args=args or {}, result=reason)
    return {"allowed": verdict == Verdict.ALLOW,
            "requires_confirmation": verdict == Verdict.CONFIRM,
            "verdict": verdict.value, "reason": reason, "event_hash": ev.hash}


@mcp.tool()
def record_execution(actor: str, tool: str, success: bool,
                     args: dict | None = None, result: str = "") -> dict:
    """Record that an allowed/confirmed action executed (or failed)."""
    ev = log().record(
        actor, tool, "executed" if success else "failed",
        args=args or {}, result=result,
    )
    return {"ok": True, "event_hash": ev.hash}


@mcp.tool()
def recent_events(n: int = 20) -> list[dict]:
    """Return recent audit events."""
    return log().recent(n)


@mcp.tool()
def verify_integrity() -> dict:
    """Verify the append-only hash chain is intact."""
    ok, line = log().verify()
    return {"ok": ok, "bad_line": line}


@mcp.tool()
def add_rule(verdict: str, tool: str, path_glob: str | None = None,
             reason: str = "") -> dict:
    """Add a runtime policy rule (prepended)."""
    from .policy import Rule
    v = Verdict(verdict)
    _policy.rules.insert(0, Rule(v, tool, path_glob, reason))
    return {"ok": True, "rules": len(_policy.rules)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
