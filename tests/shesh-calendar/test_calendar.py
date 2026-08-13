"""Offline tests for the iCalendar parser and MCP server."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_calendar import parser  # noqa: E402

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:1@test
SUMMARY:Team standup
DTSTART:20260810T090000
DTEND:20260810T093000
DESCRIPTION:Daily sync
LOCATION:Room A
END:VEVENT
BEGIN:VEVENT
UID:2@test
SUMMARY:Lunch with Sam
DTSTART:20260811T120000
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_basic(tmp_path):
    f = tmp_path / "cal.ics"
    f.write_text(ICS)
    events = parser.parse_ics(f)
    assert len(events) == 2
    e0 = events[0]
    assert e0.summary == "Team standup"
    assert e0.start == "2026-08-10T09:00:00"
    assert e0.end == "2026-08-10T09:30:00"
    assert e0.location == "Room A"


def test_unfolding(tmp_path):
    f = tmp_path / "fold.ics"
    f.write_text(
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\nSUMMARY:Long\r\n title\r\nDTSTART:20260101\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    events = parser.parse_ics(f)
    assert events[0].summary == "Longtitle"


def test_scan_dir(tmp_path):
    (tmp_path / "a.ics").write_text(ICS)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.ics").write_text(ICS)
    events = parser.scan_dir(tmp_path)
    assert len(events) == 4


def test_parse_missing_file(tmp_path):
    assert parser.parse_ics(tmp_path / "nope.ics") == []


def test_to_dict(tmp_path):
    f = tmp_path / "c.ics"
    f.write_text(ICS)
    d = parser.parse_ics(f)[0].to_dict()
    assert d["summary"] == "Team standup" and "start" in d


def test_iso_date_only():
    assert parser._to_iso("20260101") == "2026-01-01"
