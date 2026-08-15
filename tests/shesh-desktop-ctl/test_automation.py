"""Tests for the guarded proxy to computer-use-linux (ADR-0020).

The upstream binary is never invoked here; both the binary lookup and the
runner are injected.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shesh_desktop_ctl import automation as a  # noqa: E402

INSTALLED = lambda _n: "/usr/bin/computer-use-linux"  # noqa: E731
MISSING = lambda _n: None                              # noqa: E731


def runner(stdout="{}", code=0, stderr="", capture=None):
    def run(argv, **kw):
        if capture is not None:
            capture.append(argv)
        return subprocess.CompletedProcess(argv, code, stdout, stderr)
    return run


# ── the confirmation gate ───────────────────────────────────────────────────

@pytest.mark.parametrize("tool", sorted(a.REQUIRES_CONFIRM))
def test_acting_tools_refuse_without_confirmation(tool):
    """An agent that can click and type can do anything the operator can."""
    r = a.call(tool, {}, runner=runner(), which=INSTALLED)
    assert r["ok"] is False
    assert r["confirm_required"] is True


@pytest.mark.parametrize("tool", sorted(a.READ_ONLY))
def test_reading_tools_need_no_confirmation(tool):
    r = a.call(tool, {}, runner=runner('{"x":1}'), which=INSTALLED)
    assert r["ok"] is True


def test_confirmed_action_reaches_the_binary():
    calls = []
    r = a.call("click", {"x": 10, "y": 20}, confirm=True,
               runner=runner(capture=calls), which=INSTALLED)
    assert r["ok"] is True
    payload = json.loads(calls[0][-1])
    assert payload == {"tool": "click", "arguments": {"x": 10, "y": 20}}


def test_confirmation_is_not_forwarded_as_an_argument():
    """confirm is a gate in this layer, not a parameter of the upstream tool."""
    calls = []
    a.call("type_text", {"text": "hi"}, confirm=True,
           runner=runner(capture=calls), which=INSTALLED)
    assert "confirm" not in json.loads(calls[0][-1])["arguments"]


# ── input validation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool", ["rm -rf /", "a;b", "$(x)", "../etc", "", "a b"])
def test_unsafe_tool_names_are_refused(tool):
    r = a.call(tool, {}, confirm=True, runner=runner(), which=INSTALLED)
    assert r["ok"] is False
    assert "unsafe" in r["error"] or "unknown" in r["error"]


def test_unknown_tool_lists_what_is_available():
    r = a.call("teleport", {}, confirm=True, runner=runner(), which=INSTALLED)
    assert r["ok"] is False
    assert "screenshot" in r["read_only"]
    assert "click" in r["requires_confirm"]


# ── a missing upstream is reported, never raised ────────────────────────────

def test_missing_binary_is_reported_with_a_remedy():
    r = a.call("screenshot", runner=runner(), which=MISSING)
    assert r["ok"] is False
    assert "not installed" in r["error"]
    assert "ADR-0020" in r["remedy"]


def test_missing_binary_still_refuses_unconfirmed_actions():
    """Absence must not become an accidental allow."""
    r = a.call("click", {}, runner=runner(), which=MISSING)
    assert r["ok"] is False


def test_available_reflects_the_lookup():
    assert a.available(INSTALLED) is True
    assert a.available(MISSING) is False


# ── doctor ──────────────────────────────────────────────────────────────────

def test_doctor_reports_ready_when_there_are_no_blockers():
    out = json.dumps({"readiness": {"can_query_windows": True}, "blockers": []})
    r = a.doctor(runner=runner(out), which=INSTALLED)
    assert r["ok"] is True and r["blockers"] == []


def test_doctor_reports_blockers():
    out = json.dumps({"readiness": {}, "blockers": ["at_spi_bus"]})
    r = a.doctor(runner=runner(out), which=INSTALLED)
    assert r["ok"] is False and "at_spi_bus" in r["blockers"]


def test_doctor_handles_non_json_output():
    r = a.doctor(runner=runner("not json"), which=INSTALLED)
    assert r["ok"] is False and "JSON" in r["error"]


def test_doctor_without_the_binary_points_at_the_decision():
    r = a.doctor(which=MISSING)
    assert r["ok"] is False
    assert "computer-use-linux" in r["adopted_from"]


# ── failure handling ────────────────────────────────────────────────────────

def test_nonzero_exit_is_surfaced():
    r = a.call("screenshot", runner=runner("", 1, "display not found"),
               which=INSTALLED)
    assert r["ok"] is False and "display not found" in r["error"]


def test_timeout_is_reported_not_raised():
    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 30)
    r = a.call("screenshot", runner=slow, which=INSTALLED)
    assert r["ok"] is False and "timed out" in r["error"]


def test_non_json_success_is_still_returned():
    r = a.call("screenshot", runner=runner("saved to /tmp/x.png"), which=INSTALLED)
    assert r["ok"] is True and "saved to" in r["output"]
