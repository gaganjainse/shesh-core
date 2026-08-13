"""ACP JSON-RPC message types and helpers.

This is a small, typed subset of the Agent Client Protocol sufficient for an
editor to drive Shesh. It is intentionally transport-agnostic so it can be unit
tested without stdio. See docs/ACP_A2A.md.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ACP capability flags we advertise.
CAPABILITIES = {
    "fs": {"readTextFile": True, "writeTextFile": True, "list": True},
    "terminal": {"create": True, "exec": True},
    "prompts": {"stream": True},
    "permissions": {"request": True},
}


@dataclass
class PermissionRequest:
    kind: str          # "fs.write" | "terminal.exec" | ...
    detail: str
    allowed: bool = False


@dataclass
class Session:
    id: str
    cwd: str
    allow: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False


def request(id: int | str, method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 request."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def notification(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 notification (no id)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def success(id: int | str, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def error(id: int | str, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# Permission policy mirrors the Brain: auto/confirm/forbid.
def decide(kind: str, policy: Callable[[str], str]) -> bool:
    """Return True if an action is allowed by the policy ('allow'|'ask'|'deny')."""
    verdict = policy(kind)
    if verdict == "allow":
        return True
    if verdict == "deny":
        return False
    return False  # "ask" -> denied until a real client approves (tests override)
