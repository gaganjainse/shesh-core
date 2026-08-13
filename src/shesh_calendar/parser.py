"""Minimal iCalendar (.ics) parser for VEVENT entries.

We avoid a heavy icalendar dependency: parse only the fields needed for
'agenda' views (SUMMARY, DTSTART, DTEND, DESCRIPTION). Dates are returned
as ISO strings. Timezone-naive events are passed through as-is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Event:
    uid: str = ""
    summary: str = ""
    start: str = ""
    end: str = ""
    description: str = ""
    location: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "uid": self.uid, "summary": self.summary,
            "start": self.start, "end": self.end,
            "description": self.description, "location": self.location,
            "source": self.source,
        }


def _unfold(lines: list[str]) -> list[str]:
    """iCalendar line unfolding (continuation lines start with space/tab)."""
    out: list[str] = []
    for line in lines:
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _params(key: str) -> tuple[str, dict]:
    """Split 'DTSTART;TZID=Asia/Kolkata:20240101T100000' into (key, params)."""
    if ":" not in key:
        return key, {}
    name, _, value = key.partition(":")
    parts = name.split(";")
    key = parts[0]
    params = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    return key, {"params": params, "value": value}


def _to_iso(raw: str) -> str:
    """Convert 20240101T100000 or 20240101 to ISO-8601."""
    raw = raw.strip()
    if re.match(r"^\d{8}T\d{6}", raw):
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}"
    if re.match(r"^\d{8}", raw):
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw  # already ISO or with TZID


def parse_ics(path: Path) -> list[Event]:
    if not path.exists():
        return []
    lines = _unfold(path.read_text(encoding="utf-8", errors="replace").splitlines())
    events: list[Event] = []
    cur: Event | None = None
    in_event = False
    for line in lines:
        key, info = _params(line)
        key = key.upper()
        if key == "BEGIN" and info.get("value") == "VEVENT":
            cur = Event(source=str(path))
            in_event = True
        elif key == "END" and info.get("value") == "VEVENT" and cur:
            events.append(cur)
            cur = None
            in_event = False
        elif in_event and cur is not None:
            val = info.get("value", "")
            if key == "SUMMARY":
                cur.summary = val
            elif key == "DTSTART":
                cur.start = _to_iso(val)
            elif key == "DTEND":
                cur.end = _to_iso(val)
            elif key == "UID":
                cur.uid = val
            elif key == "DESCRIPTION":
                cur.description = val
            elif key == "LOCATION":
                cur.location = val
    return events


def scan_dir(directory: Path) -> list[Event]:
    """Read every .ics file under a vdir and return all events."""
    directory = Path(directory)
    if not directory.exists():
        return []
    out: list[Event] = []
    for ics in sorted(directory.rglob("*.ics")):
        out.extend(parse_ics(ics))
    return out
