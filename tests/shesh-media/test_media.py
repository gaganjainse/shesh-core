"""Offline tests for media tools (runner is faked)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import shesh_media.server as srv


def test_screenshot_missing_grim(monkeypatch):
    monkeypatch.setattr(srv.shutil, "which", lambda x: None)
    r = srv.screenshot()
    assert r["ok"] is False and "grim" in r["error"]


def test_screenshot_full(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "SHOT_DIR", tmp_path)
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/grim")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (0, ""))
    # Make the output file appear as if grim created it.
    def fake_run(cmd, timeout=60):
        if "grim" in cmd[0]:
            Path(cmd[-1]).write_bytes(b"\x89PNG")
        return 0, ""
    monkeypatch.setattr(srv, "_run", fake_run)
    r = srv.screenshot(copy=False)
    assert r["ok"] is True
    assert Path(r["path"]).exists()


def test_screenshot_region_needs_slurp(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "SHOT_DIR", tmp_path)
    # grim present, slurp absent
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/grim" if x == "grim" else None)
    r = srv.screenshot(region=True)
    assert r["ok"] is False and "slurp" in r["error"]


def test_recording_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "SHOT_DIR", tmp_path)
    monkeypatch.setattr(srv, "PID_FILE", tmp_path / "recording.pid")

    class FakeP:
        pid = 4242
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/wf-recorder")
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: FakeP())
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: (0, ""))

    started = srv.start_recording()
    assert started["ok"] is True and started["pid"] == 4242
    again = srv.start_recording()
    assert again["ok"] is False  # already recording

    stopped = srv.stop_recording()
    assert stopped["ok"] is True


def test_set_wallpaper_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/hyprctl")
    r = srv.set_wallpaper(str(tmp_path / "nope.jpg"))
    assert r["ok"] is False


def test_set_wallpaper(monkeypatch, tmp_path):
    img = tmp_path / "w.jpg"
    img.write_bytes(b"jpg")
    calls = []
    monkeypatch.setattr(srv.shutil, "which", lambda x: "/usr/bin/hyprctl")
    monkeypatch.setattr(srv, "_run", lambda cmd, timeout=60: calls.append(cmd) or (0, ""))
    r = srv.set_wallpaper(str(img))
    assert r["ok"] is True
    assert any("hyprpaper" in c for c in calls)
