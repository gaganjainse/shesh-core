#!/usr/bin/env python3
"""Shesh MCP server — Hyprland control via hyprctl.

Exposes workspace, window, focus and visual-effect controls to Newelle (stdio MCP).
License: GPL-3.0   See docs/SHESH/06_SHESH_AGENT.md
"""
from __future__ import annotations

import json
import subprocess

from shesh_audit.mcp_guard import GuardedMCP as _MCP

mcp = _MCP("shesh-shell")


def _hypr_json(*args: str):
    r = subprocess.run(
        ["hyprctl", "-j", *args], capture_output=True, text=True
    )
    out = r.stdout.strip()
    if not out:
        return {"ok": False, "stderr": r.stderr.strip()}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"ok": True, "raw": out}


def _hypr_dispatch(*args: str) -> str:
    r = subprocess.run(
        ["hyprctl", "dispatch", *args], capture_output=True, text=True
    )
    return r.stdout.strip() or r.stderr.strip()


def _keyword(key: str, value: str) -> str:
    r = subprocess.run(
        ["hyprctl", "--keyword", f"{key}={value}"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() or r.stderr.strip()


@mcp.tool()
def switch_workspace(number: int) -> str:
    """Switch to Hyprland workspace N (typically 1-10)."""
    return _hypr_dispatch("workspace", str(number))


@mcp.tool()
def move_window_to_workspace(number: int) -> str:
    """Move the currently focused window to workspace N."""
    return _hypr_dispatch("movetoworkspace", str(number))


@mcp.tool()
def get_active_window() -> dict:
    """Return JSON info about the currently focused window."""
    return _hypr_json("activewindow")


@mcp.tool()
def list_workspaces() -> list:
    """List all workspaces with their active window and monitor."""
    return _hypr_json("workspaces")


@mcp.tool()
def focus_window(query: str) -> str:
    """Focus a window by title or class substring, e.g. 'firefox' or 'code'."""
    return _hypr_dispatch("focuswindow", f"title:{query}")


@mcp.tool()
def set_opacity(active: float = 1.0, inactive: float = 0.92) -> str:
    """Set active/inactive window opacity (0.0-1.0). Lower inactive improves focus."""
    a = _keyword("decoration:active_opacity", str(active))
    b = _keyword("decoration:inactive_opacity", str(inactive))
    return f"{a}; {b}".strip("; ")


@mcp.tool()
def set_power_saver_visuals(enabled: bool) -> str:
    """Reduce blur/shadows for battery (enabled=true) or restore full visuals (false)."""
    if enabled:
        _keyword("decoration:blur:passes", "1")
        _keyword("decoration:shadow:enabled", "0")
        return "Power-saver visuals: blur reduced, shadows off"
    _keyword("decoration:blur:passes", "3")
    _keyword("decoration:shadow:enabled", "1")
    return "Full visuals restored"


@mcp.tool()
def toggle_floating() -> str:
    """Toggle the focused window between tiled and floating."""
    return _hypr_dispatch("togglefloating")


@mcp.tool()
def fullscreen() -> str:
    """Toggle fullscreen for the focused window."""
    return _hypr_dispatch("fullscreen")


def main() -> None:
    """Entry point for the shesh-shell-mcp console script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
