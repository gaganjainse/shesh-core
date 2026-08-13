"""Local-first calendar/event tools for Shesh.

Reads iCalendar (.ics) files from a vdir (as used by vdirsyncer/khal) and
exposes upcoming events. It does NOT talk to network calendars directly —
sync is delegated to vdirsyncer, keeping this component simple, testable,
and offline-first. Writes go to a local calendar dir.
"""
from __future__ import annotations

__version__ = "0.1.0"
