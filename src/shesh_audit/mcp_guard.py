"""MCP server guard: enforce the Guard on every tool call.

Two enforcement seams, one policy/log path:

1. ``GuardedMCP.tool()`` — wraps *directly registered* tools so the policy
   check runs before the wrapped function and execution is recorded after.
   Works even when a tool object is invoked in-process (unit tests).
2. ``GuardMiddleware`` — a FastMCP 3 server middleware covering tools that
   never pass through our decorator: mounted servers and stdio/HTTP proxies
   (shesh-mcp-bundle). It runs the same Guard on the protocol boundary.

Exactly-once guarantee: wrapped tools are marked ``_shesh_guarded``; the
middleware skips those (they were already checked/logged at the function
seam), so a call is never double-logged regardless of the layer it enters.

Usage:
    from fastmcp import FastMCP
    from shesh_audit.mcp_guard import GuardedMCP

    mcp = GuardedMCP("shesh-system")

    @mcp.tool()
    def set_power_profile(profile: str) -> dict:
        ...

    # and, for proxies/mounts:
    mcp.mount(other_server, namespace="fs")  # also guarded
"""
from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from shesh_audit.gate import Guard
from shesh_audit.policy import Verdict
from shesh_audit.tool_pins import verify_tool

GUARDED_MARK = "_shesh_guarded"


class GuardDeniedError(ToolError):
    """A tool call was denied by policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"denied: {reason}")


class GuardMiddleware(Middleware):
    """Protocol-seam guard: policy-checks tool calls not already wrapped."""

    def __init__(self, guard: Guard, actor: str) -> None:
        self._guard = guard
        self._actor = actor

    async def on_call_tool(
        self, context: MiddlewareContext, call_next
    ) -> ToolResult:
        msg = context.message
        name = getattr(msg, "name", "unknown")
        args = dict(getattr(msg, "arguments", None) or {})
        # Mounted servers namespace their tools ("fs__read_file"); the guard
        # sees the full wire name, which is the honest audit identifier.
        tool = None
        fctx = context.fastmcp_context
        if fctx is not None:
            try:
                tool = await fctx.fastmcp.get_tool(name)
            except Exception:  # noqa: BLE001 — middleware must not break calls
                tool = None
        # Only FunctionTools carry .fn (marked when GuardedMCP.tool wrapped
        # them). Proxied/mounted tools never have it — they enter only here.
        fn = getattr(tool, "fn", None) if tool is not None else None
        if fn is not None and getattr(fn, GUARDED_MARK, False):
            return await call_next(context)  # wrapped seam already handles it

        # Protocol-seam rug-pull defense: mounted/proxied tools never saw the
        # decorator, so verify their wire description against the pins here.
        if tool is not None:
            verify_tool(self._actor, name, getattr(tool, "description", None) or "", None)

        decision = self._guard.check(name, args, actor=self._actor)
        if decision.verdict == Verdict.DENY.value:
            self._guard.log_execution(
                name, False, actor=self._actor, args=args,
                result=f"denied: {decision.reason}",
            )
            raise GuardDeniedError(decision.reason)
        try:
            result = await call_next(context)
        except Exception as e:
            self._guard.log_execution(
                name, False, actor=self._actor, args=args,
                result=str(e)[:200],
            )
            raise
        self._guard.log_execution(
            name, True, actor=self._actor, args=args,
            result=str(result)[:200],
        )
        return result


class GuardedMCP(FastMCP):
    """A FastMCP that runs every tool — direct or proxied — through a Guard."""

    def __init__(self, name: str, guard: Guard | None = None, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.guard = guard or Guard()
        self._actor = name
        self.add_middleware(GuardMiddleware(self.guard, actor=name))

    def tool(self, *tool_args, **tool_kwargs):  # type: ignore[override]
        """Override tool() to wrap the registered function with policy checks."""
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            actor = self._actor
            # Rug-pull/poisoning defense: the tool definition (name, docstring
            # description, signature) must match its integrity pin. First boot
            # learns pins loudly; later drift refuses registration (ToolPinDrift).
            verify_tool(self.name, getattr(fn, "__name__", "unknown"),
                        inspect.getdoc(fn) or "", fn)

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                tool_name = getattr(fn, "__name__", "unknown")
                # Merge args/kwargs into a dict the policy can inspect.
                inspect_args = {f"arg{i}": a for i, a in enumerate(args)}
                inspect_args.update(kwargs)

                decision = self.guard.check(
                    tool_name, inspect_args, actor=actor)

                if decision.verdict == Verdict.DENY.value:
                    return {"ok": False, "error": f"denied: {decision.reason}"}
                if decision.verdict == Verdict.CONFIRM.value:
                    # A confirmation is never authorization. Hosts without an
                    # approval channel receive a non-executing result.
                    return {
                        "ok": False,
                        "needs_confirmation": True,
                        "error": f"confirmation required: {decision.reason}",
                    }
                try:
                    result = fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    # Telemetry boundary: any tool failure is recorded with its
                    # message, then re-raised unchanged. Nothing is swallowed.
                    self.guard.log_execution(
                        tool_name, False, actor=actor,
                        args=inspect_args, result=str(e)[:200])
                    raise
                self.guard.log_execution(
                    tool_name,
                    success=not (isinstance(result, dict) and result.get("ok") is False),
                    actor=actor, args=inspect_args,
                    result=str(result)[:200],
                )
                return result

            wrapper.__dict__[GUARDED_MARK] = True
            # Register the wrapper, not the raw function.
            return super(GuardedMCP, self).tool(*tool_args, **tool_kwargs)(wrapper)

        return decorator

# Capability levels for tool maturity classification
CAPABILITY_CHOICES = ("supported", "experimental", "stub")

def tool_fingerprint(name: str, description: str, signature: str,
                     capability: str = "supported") -> str:
    """Return SHA-256 fingerprint of tool definition including capability level.
    
    Args:
        name: Tool name
        description: Tool description
        signature: Tool function signature
        capability: One of CAPABILITY_CHOICES: supported, experimental, stub
    
    Returns:
        SHA-256 hex digest of the tool fingerprint
    """
    if capability not in CAPABILITY_CHOICES:
        raise ValueError(f"Invalid capability: {{capability}}; must be one of {{CAPABILITY_CHOICES}}")
    import json
    blob = json.dumps({{"name": name, "description": description, "signature": signature,
                       "capability": capability}}, sort_keys=True)
    return hashlib.sha256(blob).hexdigest()
