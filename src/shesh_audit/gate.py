"""Reusable policy gate for MCP tools.

Other Shesh components import `guard(...)` to check an action against policy
and log the decision before executing. The gate loads the same default policy
as the audit server, but can be pointed at a custom rules file.

Usage:
    from shesh_audit.gate import guard, Guard

    g = Guard()
    decision = g.check("write_file", {"path": "/home/u/notes/x.md"})
    if decision.allowed:
        ...do the thing...
        g.log_execution("write_file", True, args={"path": ...})
    elif decision.requires_confirmation:
        ...ask the user...
    else:
        raise PermissionError(decision.reason)
"""
from __future__ import annotations

from dataclasses import dataclass

from .kernel_bridge import KernelBridge, KernelEventKind
from .log import AuditLog
from .policy import Policy, load_policy


@dataclass
class Decision:
    allowed: bool
    requires_confirmation: bool
    verdict: str
    reason: str


class Guard:
    """Wraps a Policy + AuditLog so every tool call is decided and recorded."""

    def __init__(self, policy: Policy | None = None, audit: AuditLog | None = None,
                 bridge: KernelBridge | None = None) -> None:
        self.policy = policy or load_policy()
        self.audit = audit or AuditLog()
        self.bridge = bridge

    def check(self, tool: str, args: dict | None = None, *, actor: str = "agent") -> Decision:
        verdict, reason = self.policy.decide(tool, args)
        self.audit.record(actor, tool, verdict.value, args=args or {}, result=reason)
        if self.bridge is not None:
            kind = {
                "allow": KernelEventKind.TOOL_REQUESTED,
                "confirm": KernelEventKind.CONFIRMATION_REQUESTED,
                "deny": KernelEventKind.POLICY_DENIED,
            }[verdict.value]
            self.bridge.emit(kind, {"actor": actor, "tool": tool, "args": args or {}})
        return Decision(
            allowed=(verdict.value == "allow"),
            requires_confirmation=(verdict.value == "confirm"),
            verdict=verdict.value,
            reason=reason,
        )

    def log_execution(self, tool: str, success: bool, *, actor: str = "agent",
                     args: dict | None = None, result: str = "") -> None:
        self.audit.record(actor, tool, "executed" if success else "failed",
                          args=args or {}, result=result)
        if self.bridge is not None:
            self.bridge.emit(
                KernelEventKind.TOOL_COMPLETED if success else KernelEventKind.TOOL_FAILED,
                {"actor": actor, "tool": tool, "result": result[:200]})

    def is_allowed(self, tool: str, args: dict | None = None, *, actor: str = "agent") -> bool:
        """Convenience: True only if the action is silently allowed."""
        return self.check(tool, args, actor=actor).allowed
