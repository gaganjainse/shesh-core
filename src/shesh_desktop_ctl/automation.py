"""Guarded proxy to the computer-use-linux desktop automation server.

Adopted rather than reimplemented: see ADR-0020. The upstream is a separate
Rust process speaking the Model Context Protocol over stdio. It is never
exposed to an agent directly, because a client configured against it would
bypass the policy engine. Every call is proxied here so the guard sees it.

Input injection is the highest-risk surface in the fleet: an agent that can
click and type can do anything the operator can. Those calls therefore default
to requiring confirmation, independent of the policy engine's own verdict.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

BINARY = os.environ.get("SHESH_CUL_BINARY", "computer-use-linux")
DEFAULT_TIMEOUT = 30

# Reading the screen is safe. Acting on it is not. The split is deliberate and
# does not rely on the upstream's own classification.
READ_ONLY = frozenset({
    "doctor", "apps", "state", "screenshot", "windows",
    "list_windows", "focused_window", "accessibility_tree",
})
REQUIRES_CONFIRM = frozenset({
    "click", "double_click", "right_click", "drag", "scroll",
    "type_text", "press_key", "activate_window", "move_window",
    "resize_window", "close_window", "invoke_action",
})


@dataclass
class Result:
    ok: bool
    data: dict | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out: dict = {"ok": self.ok}
        if self.data is not None:
            out.update(self.data)
        if self.error:
            out["error"] = self.error
        out.update(self.meta)
        return out


Runner = Callable[..., subprocess.CompletedProcess]


def _run(argv: list[str], *, timeout: int = DEFAULT_TIMEOUT
         ) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def available(which: Callable[[str], str | None] = shutil.which) -> bool:
    return which(BINARY) is not None


def doctor(runner: Runner = _run,
           which: Callable[[str], str | None] = shutil.which) -> dict:
    """Report whether desktop automation is usable on this machine.

    The upstream needs the accessibility bus enabled and a compositor backend
    it recognises. Reporting that plainly is more useful than a failed click.
    """
    if not available(which):
        return Result(
            False,
            error=f"{BINARY} is not installed",
            meta={"remedy": "Install computer-use-linux; see ADR-0020.",
                  "adopted_from": "https://github.com/agent-sh/computer-use-linux"},
        ).as_dict()
    try:
        p = runner([BINARY, "doctor"], timeout=DEFAULT_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as exc:
        return Result(False, error=str(exc)).as_dict()

    try:
        report = json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        return Result(False, error="doctor did not return JSON",
                      meta={"raw": (p.stdout or p.stderr)[:400]}).as_dict()

    blockers = report.get("blockers") or []
    return Result(not blockers, data={"readiness": report.get("readiness", {}),
                                      "blockers": blockers}).as_dict()


def call(tool: str, arguments: dict | None = None, *, confirm: bool = False,
         runner: Runner = _run,
         which: Callable[[str], str | None] = shutil.which) -> dict:
    """Invoke one upstream tool through the guard.

    A tool that moves the pointer, presses a key, or changes a window requires
    confirm=True. The refusal is independent of the policy engine so that a
    permissive policy cannot silently enable blind clicking.
    """
    if not isinstance(tool, str) or not tool.replace("_", "").isalnum():
        return Result(False, error=f"unsafe tool name: {tool!r}").as_dict()

    if not available(which):
        return Result(False, error=f"{BINARY} is not installed",
                      meta={"remedy": "See ADR-0020."}).as_dict()

    if tool in REQUIRES_CONFIRM and not confirm:
        return Result(
            False,
            error=(f"{tool} acts on the desktop and cannot be undone; "
                   f"call again with confirm=True"),
            meta={"confirm_required": True, "tool": tool},
        ).as_dict()

    if tool not in READ_ONLY and tool not in REQUIRES_CONFIRM:
        return Result(False, error=f"unknown tool: {tool}",
                      meta={"read_only": sorted(READ_ONLY),
                            "requires_confirm": sorted(REQUIRES_CONFIRM)}).as_dict()

    payload = json.dumps({"tool": tool, "arguments": arguments or {}})
    try:
        p = runner([BINARY, "call", "--json", payload], timeout=DEFAULT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return Result(False, error=f"{tool} timed out").as_dict()
    except (subprocess.SubprocessError, OSError) as exc:
        return Result(False, error=str(exc)).as_dict()

    if p.returncode != 0:
        return Result(False, error=(p.stderr or p.stdout or "call failed").strip()
                      ).as_dict()
    try:
        return Result(True, data=json.loads(p.stdout or "{}")).as_dict()
    except json.JSONDecodeError:
        return Result(True, data={"output": (p.stdout or "").strip()}).as_dict()
