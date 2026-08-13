"""Offline tests for shesh-system (subprocess calls mocked)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import shesh_system.server as srv  # noqa: E402


@pytest.fixture(autouse=True)
def _no_hyprctl(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda _: None)


def test_set_power_profile_rejects_unknown():
    assert "Unknown mode" in srv.set_power_profile("turbo")


@pytest.mark.parametrize("mode,profile", [
    ("gaming", "performance"),
    ("performance", "performance"),
    ("balanced", "balanced"),
    ("battery", "power-saver"),
])
def test_set_power_profile_valid(monkeypatch, mode, profile):
    calls = []
    monkeypatch.setattr(srv, "_run", lambda cmd, **_k: (calls.append(cmd), "")[1])
    result = srv.set_power_profile(mode)
    assert profile in result
    assert ["powerprofilesctl", "set", profile] in calls


def test_mux_status_without_binary(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda _: None)
    assert "not installed" in srv.mux_status()


def test_run_handles_missing_command():
    # _run should swallow FileNotFoundError and report it
    out = srv._run(["definitely-not-a-real-command-xyz"])
    assert "command not found" in out
