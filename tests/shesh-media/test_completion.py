"""Completion tests: honesty contract for list_sinks (no fabricated sink
names) and real volume get/set via wpctl."""
from __future__ import annotations

import shesh_media.server as srv


def test_sinks_never_fabricated(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: None)
    res = srv.list_sinks()
    assert res["ok"] is False and res["sinks"] == []
    assert res["offline"] is True and "wpctl" in res["reason"]
    assert "stub" not in " ".join(res["sinks"])


def test_sinks_real_when_wpctl_answers(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wpctl")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (0, "sink-a\nsink-b"))
    res = srv.list_sinks()
    assert res["ok"] is True and res["sinks"] == ["sink-a", "sink-b"]
    assert res["offline"] is False


def test_sinks_cli_failure_reports_reason(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wpctl")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (1, "pipewire down"))
    res = srv.list_sinks()
    assert res["ok"] is False and res["sinks"] == []
    assert res["reason"] == "pipewire down"


def test_get_volume_parses_muted_state(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wpctl")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (0, "Volume: 0.45 [MUTED]"))
    res = srv.get_volume()
    assert res["ok"] is True and res["volume"] == 0.45 and res["muted"] is True


def test_get_volume_unparseable_is_honest(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wpctl")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (0, "garbage-out"))
    res = srv.get_volume()
    assert res["ok"] is False and "unparseable" in res["error"]


def test_set_volume_bounds_and_call(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wpctl")
    calls = []
    monkeypatch.setattr(srv, "_run",
                        lambda cmd, timeout=60: calls.append(cmd) or (0, ""))
    assert srv.set_volume(1.5)["ok"] is False  # over-cap rejected by policy
    assert srv.set_volume(-0.1)["ok"] is False
    assert srv.set_volume("loud")["ok"] is False
    res = srv.set_volume(0.5)
    assert res["ok"] is True and res["volume"] == 0.5
    assert calls[0][:3] == ["wpctl", "set-volume", "-l"]
    assert "1.0" in calls[0]  # hard cap flag passed through


def test_volume_tools_fail_honestly_without_wpctl(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: None)
    assert srv.get_volume()["ok"] is False
    assert srv.set_volume(0.5)["ok"] is False
