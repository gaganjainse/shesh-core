"""MCP server guard: enforce the Guard on every tool call.

Two enforcement seams, one policy/log path:

1. ``GuardedMCP.tool()`` — wraps directly registered tools so the policy
   check runs before the wrapped function and execution is recorded after.
2. ``GuardMiddleware`` — a FastMCP middleware covering mounted/proxied tools.

Exactly-once guarantee: wrapped tools are marked ``_shesh_guarded``; the
middleware skips those because they were already checked/logged at the function
seam.
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

from .gate import Guard
from .policy import Verdict
from .tool_pins import finish_bootstrap, verify_tool

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
        tool = None
        fctx = context.fastmcp_context
        if fctx is not None:
            try:
                tool = await fctx.fastmcp.get_tool(name)
            except Exception:  # noqa: BLE001 — missing introspection must not bypass the guard
                tool = None

        fn = getattr(tool, "fn", None) if tool is not None else None
        if fn is not None and getattr(fn, GUARDED_MARK, False):
            return await call_next(context)

        if tool is not None:
            verify_tool(
                self._actor,
                name,
                getattr(tool, "description", None) or "",
                None,
            )

        decision = self._guard.check(name, args, actor=self._actor)
        if decision.verdict == Verdict.DENY.value:
            self._guard.log_execution(
                name,
                False,
                actor=self._actor,
                args=args,
                result=f"denied: {decision.reason}",
            )
            raise GuardDeniedError(decision.reason)
        try:
            result = await call_next(context)
        except Exception as e:
            self._guard.log_execution(
                name, False, actor=self._actor, args=args, result=str(e)[:200]
            )
            raise
        self._guard.log_execution(
            name, True, actor=self._actor, args=args, result=str(result)[:200]
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
            verify_tool(
                self.name,
                getattr(fn, "__name__", "unknown"),
                inspect.getdoc(fn) or "",
                fn,
            )

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                tool_name = getattr(fn, "__name__", "unknown")
                inspect_args = {f"arg{i}": a for i, a in enumerate(args)}
                inspect_args.update(kwargs)
                decision = self.guard.check(tool_name, inspect_args, actor=actor)

                if decision.verdict == Verdict.DENY.value:
                    self.guard.log_execution(
                        tool_name,
                        False,
                        actor=actor,
                        args=inspect_args,
                        result=f"denied: {decision.reason}",
                    )
                    raise GuardDeniedError(decision.reason)

                try:
                    result = fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    self.guard.log_execution(
                        tool_name,
                        False,
                        actor=actor,
                        args=inspect_args,
                        result=str(e)[:200],
                    )
                    raise
                self.guard.log_execution(
                    tool_name,
                    success=not (
                        isinstance(result, dict) and result.get("ok") is False
                    ),
                    actor=actor,
                    args=inspect_args,
                    result=str(result)[:200],
                )
                return result

            wrapper.__dict__[GUARDED_MARK] = True
            return super(GuardedMCP, self).tool(*tool_args, **tool_kwargs)(wrapper)

        return decorator

    def run(self, *args, **kwargs):  # type: ignore[override]
        """Stop first-boot TOFU learning before accepting client requests."""
        finish_bootstrap(self._actor)
        return super().run(*args, **kwargs)
