"""Offline tests for shesh-shell (subprocess calls are mocked)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import shesh_shell.server as srv  # noqa: E402


def test_switch_workspace_dispatches(monkeypatch):
    calls = []
    monkeypatch.setattr(srv, "_hypr_dispatch", lambda *a: (calls.append(a), "ok")[1])
    assert srv.switch_workspace(3) == "ok"
    assert ("workspace", "3") in calls


def test_set_opacity_calls_keyword(monkeypatch):
    kw = []
    monkeypatch.setattr(srv, "_keyword", lambda k, v: kw.append((k, v)) or "")
    srv.set_opacity(0.9, 0.8)
    assert ("decoration:active_opacity", "0.9") in kw
    assert ("decoration:inactive_opacity", "0.8") in kw


def test_power_saver_visuals(monkeypatch):
    kw = []
    monkeypatch.setattr(srv, "_keyword", lambda k, v: kw.append((k, v)) or "")
    srv.set_power_saver_visuals(True)
    assert any(k == "decoration:blur:passes" and v == "1" for k, v in kw)
    assert any(k == "decoration:shadow:enabled" and v == "0" for k, v in kw)
