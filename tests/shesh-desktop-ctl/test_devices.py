"""Tests for desktop device and session control.

Every path is exercised with an injected runner, so nothing here needs
Bluetooth hardware, a network, or a display.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shesh_desktop_ctl import devices as d  # noqa: E402
from shesh_desktop_ctl.devices import Result  # noqa: E402


def ok(stdout=""):
    return lambda cmd, **kw: Result(stdout, "", 0)


def fail(stderr="boom", code=1):
    return lambda cmd, **kw: Result("", stderr, code)


def record(stdout="", store=None):
    def runner(cmd, **kw):
        if store is not None:
            store.append(cmd)
        return Result(stdout, "", 0)
    return runner


# ── Bluetooth ───────────────────────────────────────────────────────────────

def test_bluetooth_status_parses_flags():
    r = d.bluetooth_status(runner=ok("Powered: yes\nDiscovering: no"))
    assert r == {"ok": True, "powered": True, "discovering": False}


def test_bluetooth_status_reports_a_missing_tool():
    r = d.bluetooth_status(runner=fail("bluetoothctl is not installed", 127))
    assert r["ok"] is False and "not installed" in r["error"]


def test_bluetooth_devices_parses_the_listing():
    out = "Device AA:BB:CC:DD:EE:FF Sony WH-1000XM4\nDevice 11:22:33:44:55:66 Keyboard"
    r = d.bluetooth_devices(runner=ok(out))
    assert r["ok"] and len(r["devices"]) == 2
    assert r["devices"][0] == {"mac": "AA:BB:CC:DD:EE:FF", "name": "Sony WH-1000XM4"}


def test_bluetooth_devices_ignores_noise():
    r = d.bluetooth_devices(runner=ok("Agent registered\nnonsense line"))
    assert r["ok"] and r["devices"] == []


@pytest.mark.parametrize("mac", ["nope", "AA:BB", "", "; rm -rf /"])
def test_bluetooth_connect_rejects_a_bad_mac(mac):
    """A MAC goes onto a command line; validate before it gets there."""
    r = d.bluetooth_connect(mac, runner=ok())
    assert r["ok"] is False and "MAC" in r["error"]


def test_bluetooth_connect_requires_success_in_the_output():
    """bluetoothctl exits 0 even when the connection fails."""
    r = d.bluetooth_connect("AA:BB:CC:DD:EE:FF", runner=ok("Failed to connect"))
    assert r["ok"] is False


def test_bluetooth_connect_succeeds():
    r = d.bluetooth_connect("AA:BB:CC:DD:EE:FF", runner=ok("Connection successful"))
    assert r["ok"] and r["mac"] == "AA:BB:CC:DD:EE:FF"


# ── Networking ──────────────────────────────────────────────────────────────

def test_network_status_parses_devices():
    r = d.network_status(runner=ok("wifi:connected:HomeNet\nethernet:unavailable:"))
    assert r["ok"] and len(r["devices"]) == 2
    assert r["devices"][0]["connection"] == "HomeNet"
    assert r["devices"][1]["connection"] is None


def test_wifi_list_sorts_by_signal_and_deduplicates():
    out = "Weak:20:WPA2\nStrong:90:WPA2\nStrong:85:WPA2\n:0:"
    r = d.wifi_list(runner=ok(out))
    assert [n["ssid"] for n in r["networks"]] == ["Strong", "Weak"]
    assert r["networks"][0]["signal"] == 90


def test_wifi_list_marks_open_networks():
    r = d.wifi_list(runner=ok("Cafe:70:"))
    assert r["networks"][0]["security"] == "open"


def test_wifi_connect_omits_password_when_absent():
    calls = []
    d.wifi_connect("Net", runner=record(store=calls))
    assert "password" not in calls[0]


def test_wifi_connect_passes_password_when_given():
    calls = []
    d.wifi_connect("Net", "hunter2", runner=record(store=calls))
    assert "password" in calls[0] and "hunter2" in calls[0]


# ── Brightness ──────────────────────────────────────────────────────────────

def test_brightness_get_computes_a_percentage():
    vals = iter(["600", "1000"])
    r = d.brightness_get(runner=lambda cmd, **kw: Result(next(vals), "", 0))
    assert r == {"ok": True, "raw": 600, "max": 1000, "percent": 60}


def test_brightness_get_handles_unparseable_output():
    r = d.brightness_get(runner=ok("not a number"))
    assert r["ok"] is False


@pytest.mark.parametrize("given,expected", [(0, 1), (-50, 1), (150, 100), (42, 42)])
def test_brightness_set_clamps(given, expected):
    """Zero blanks the panel; the user may not see well enough to undo it."""
    r = d.brightness_set(given, runner=ok())
    assert r["percent"] == expected


def test_brightness_set_rejects_a_non_integer():
    assert d.brightness_set("bright", runner=ok())["ok"] is False


# ── Clipboard ───────────────────────────────────────────────────────────────

def test_clipboard_get_returns_text():
    assert d.clipboard_get(runner=ok("hello"))["text"] == "hello"


def test_empty_clipboard_is_not_an_error():
    r = d.clipboard_get(runner=fail("Nothing is copied: clipboard empty"))
    assert r["ok"] is True and r["text"] == ""


# ── Session ─────────────────────────────────────────────────────────────────

def test_lock_needs_no_confirmation():
    """Locking is reversible and safe, so it should not nag."""
    assert d.session_action("lock", runner=ok())["ok"] is True


@pytest.mark.parametrize("action", ["suspend", "hibernate", "logout",
                                    "reboot", "poweroff"])
def test_destructive_session_actions_require_confirmation(action):
    r = d.session_action(action, runner=ok())
    assert r["ok"] is False
    assert r["confirm_required"] is True


def test_destructive_action_runs_once_confirmed():
    assert d.session_action("reboot", confirm=True, runner=ok())["ok"] is True


def test_confirmation_does_not_reach_the_command_line():
    calls = []
    d.session_action("reboot", confirm=True, runner=record(store=calls))
    assert calls[0] == ["systemctl", "reboot"]


def test_unknown_session_action_lists_the_valid_ones():
    r = d.session_action("selfdestruct", runner=ok())
    assert r["ok"] is False and "lock" in r["available"]


# ── Services ────────────────────────────────────────────────────────────────

def test_service_status_reports_both_fields():
    vals = iter(["active", "enabled"])
    r = d.service_status("ollama", runner=lambda c, **k: Result(next(vals), "", 0))
    assert r["active"] == "active" and r["enabled"] == "enabled"


@pytest.mark.parametrize("unit", ["a b", "unit;rm -rf /", "$(x)", "../etc"])
def test_service_names_are_validated(unit):
    assert d.service_status(unit, runner=ok())["ok"] is False
    assert d.service_restart(unit, confirm=True, runner=ok())["ok"] is False


def test_service_restart_requires_confirmation():
    r = d.service_restart("ollama", runner=ok())
    assert r["ok"] is False and r["confirm_required"] is True


def test_service_restart_runs_once_confirmed():
    assert d.service_restart("ollama", confirm=True, runner=ok())["ok"] is True


def test_failed_units_are_counted():
    out = "a.service loaded failed failed A\nb.service loaded failed failed B"
    r = d.service_list_failed(runner=ok(out))
    assert r["count"] == 2 and r["failed"] == ["a.service", "b.service"]


def test_no_failed_units():
    assert d.service_list_failed(runner=ok(""))["count"] == 0


def test_user_scope_is_passed_through():
    calls = []
    d.service_list_failed(user=True, runner=record(store=calls))
    assert "--user" in calls[0]
    calls.clear()
    d.service_list_failed(user=False, runner=record(store=calls))
    assert "--user" not in calls[0]


# ── Notifications ───────────────────────────────────────────────────────────

def test_notify_validates_urgency():
    assert d.notify("hi", urgency="screaming", runner=ok())["ok"] is False


def test_notify_sends():
    assert d.notify("Backup finished", "3.2 GB", runner=ok())["ok"] is True


# ── Shared contract ─────────────────────────────────────────────────────────

def test_a_missing_tool_never_raises():
    """An agent should get an actionable message, not a traceback."""
    missing = fail("brightnessctl is not installed", 127)
    for call in (
        lambda: d.brightness_get(runner=missing),
        lambda: d.bluetooth_status(runner=missing),
        lambda: d.network_status(runner=missing),
        lambda: d.clipboard_get(runner=missing),
        lambda: d.session_action("lock", runner=missing),
    ):
        r = call()
        assert r["ok"] is False and "error" in r
