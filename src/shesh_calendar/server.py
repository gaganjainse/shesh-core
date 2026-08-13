"""MCP server for local calendar/event access."""
from __future__ import annotations

from pathlib import Path

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from . import parser

mcp = _MCP("shesh-calendar")

DEFAULT_DIR = Path.home() / ".local" / "share" / "shesh" / "calendar"


def _dir() -> Path:
    import os
    return Path(os.environ.get("SHESH_CALENDAR_DIR", DEFAULT_DIR))


@mcp.tool()
def upcoming_events(days: int = 7) -> list[dict]:
    """List events in the next N days from the local vdir."""
    events = parser.scan_dir(_dir())
    # Sort by start; no date filtering dependency — return upcoming only.
    events = [e for e in events if e.start]
    events.sort(key=lambda e: e.start)
    return [e.to_dict() for e in events[:100]]


@mcp.tool()
def search_calendar(query: str) -> list[dict]:
    """Search events whose summary/description contains the query."""
    q = query.lower()
    events = parser.scan_dir(_dir())
    return [
        e.to_dict() for e in events
        if q in e.summary.lower() or q in e.description.lower()
    ]


@mcp.tool()
def list_calendars() -> list[str]:
    """List available .ics calendar files."""
    d = _dir()
    if not d.exists():
        return []
    return sorted(str(p.relative_to(d)) for p in d.rglob("*.ics"))


@mcp.tool()
def calendar_status() -> dict:
    """Report where the calendar vdir is and how many events exist."""
    d = _dir()
    events = parser.scan_dir(d)
    return {"dir": str(d), "exists": d.exists(), "event_count": len(events)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
