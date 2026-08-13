"""Offline tests for maintenance/health/update tools."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_system import maintenance as m  # noqa: E402


def test_check_updates_no_updates(monkeypatch):
    monkeypatch.setattr(m.shutil, "which", lambda x: "/usr/bin/checkupdates")
    monkeypatch.setattr(m, "_run", lambda cmd, timeout=60: (2, ""))
    s = m.check_updates()
    assert s.available is False


def test_check_updates_lists_packages(monkeypatch):
    monkeypatch.setattr(m.shutil, "which", lambda x: "/usr/bin/checkupdates")
    monkeypatch.setattr(m, "_run", lambda cmd, timeout=60: (0, "linux 6.0\nvim 9.0"))
    s = m.check_updates()
    assert s.available is True and s.count == 2
    assert "never auto" in s.note.lower()


def test_cache_size_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_run", lambda cmd, timeout=60: (0, "123\t/some/path"))
    sizes = m.cache_size()
    assert any(k.endswith("_mb") for k in sizes)


def test_clean_user_cache(monkeypatch):
    called = {}

    def fake_run(cmd, timeout=60):
        called["cmd"] = cmd
        return 0, ""

    monkeypatch.setattr(m, "_run", fake_run)
    m.clean_caches("user")
    assert "rm" in " ".join(called["cmd"])


def test_health_report_has_sections(monkeypatch, tmp_path):
    # Stub du and systemctl
    monkeypatch.setattr(m, "_run", lambda cmd, timeout=60: (0, "0 failed."))
    report = m.health_report()
    assert "failed_units" in report
    assert "caches" in report


def test_mcp_tools_exist():
    import shesh_system.server as srv  # noqa: F401
    # The tools are registered on the MCP instance; ensure functions exist.
    assert hasattr(srv, "check_system_updates")
    assert hasattr(srv, "clean_system_caches")
    assert hasattr(srv, "system_health")

def test_check_system_updates_is_strictly_readonly(monkeypatch):
    """Swarm #44: the update check may ONLY ever run read-only commands."""
    import shesh_system.maintenance as m

    called: list[list[str]] = []

    def fake_run(cmd, timeout=60):
        called.append(list(cmd))
        return 0, "pkg1 1.0 -> 1.1\npkg2 2.0 -> 2.1\n"

    monkeypatch.setattr(m, "_run", fake_run)
    monkeypatch.setattr(m.shutil, "which", lambda name: "/usr/bin/checkupdates")
    s = m.check_updates()
    assert s.available and s.count == 2

    monkeypatch.setattr(m.shutil, "which", lambda name: None)  # force pacman -Qu path
    s = m.check_updates()
    assert s.available

    READONLY = {"checkupdates": {"-n"}, "pacman": {"-Qu"}, "du": {"-sm"}}
    MUTATING = {"-S", "-Sy", "-Syu", "-Su", "-R", "-Rs", "-U", "--upgrade", "--refresh"}
    for cmd in called:
        assert cmd[0] in READONLY, f"unexpected command {cmd[0]} — updates check must be read-only"
        for arg in cmd[1:]:
            assert arg in READONLY[cmd[0]], f"forbidden arg {arg} to {cmd[0]}"
            assert arg not in MUTATING


def test_server_tool_reports_status(monkeypatch):
    from shesh_system import server
    from shesh_system.maintenance import UpdateStatus

    monkeypatch.setattr(
        server, "check_updates",
        lambda: UpdateStatus(True, 3, "a b c", "ok"),
    )
    res = server.check_system_updates()
    assert res["available"] is True and res["count"] == 3 and "note" in res
