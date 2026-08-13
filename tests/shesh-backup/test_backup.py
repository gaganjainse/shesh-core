"""Offline tests for shesh-backup (no restic/network needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_backup.backup import (  # noqa: E402
    BackupConfig,
    BackupState,
    backup,
    prune,
    should_run,
)
from shesh_backup.runner import Result  # noqa: E402


def make_runner(backup_ok=True, snapshots="[]"):
    def _run(cmd, **kw):
        if "backup" in cmd:
            return Result("snapshot saved", "", 0 if backup_ok else 1)
        if "snapshots" in cmd:
            return Result(snapshots, "", 0)
        if "forget" in cmd:
            return Result("pruned", "", 0)
        return Result("", "", 0)
    return _run


def test_should_run_when_due(tmp_path):
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    state = BackupState(last_run=0)
    assert should_run(cfg, state, now=10**10, on_ac=True)[0] is True


def test_skips_when_off_ac():
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    assert should_run(cfg, BackupState(), on_ac=False)[0] is False


def test_skips_when_not_configured():
    assert should_run(BackupConfig(), BackupState())[0] is False


def test_skips_when_ran_recently():
    import time
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    state = BackupState(last_run=time.time())
    assert should_run(cfg, state)[0] is False


def test_backup_runs_and_records(tmp_path):
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    state_path = tmp_path / "state.json"
    state = BackupState()
    snapshots = '[{"short_id":"abc","time":"2026-01-01"}]'
    result = backup(cfg, state, state_path, runner=make_runner(snapshots=snapshots))
    assert result["ok"] is True
    assert result["snapshots"] == 1
    assert state.last_status == "ok"
    assert state_path.exists()


def test_backup_failure_records(tmp_path):
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    state_path = tmp_path / "state.json"
    result = backup(cfg, BackupState(), state_path, runner=make_runner(backup_ok=False))
    assert result["ok"] is False
    assert BackupState.load(state_path).last_status == "failed"


def test_prune_calls_restic_forget():
    cfg = BackupConfig(repo="/repo", paths=[])
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return Result("ok", "", 0)

    prune(cfg, runner=runner)
    assert any("forget" in c and "--prune" in c for c in calls)


def test_missing_restic_reports_gracefully(tmp_path):
    def missing(cmd, **kw):
        return Result("", "command not found: restic", 127)
    cfg = BackupConfig(repo="/repo", paths=["/home"])
    result = backup(cfg, BackupState(), tmp_path / "s.json", runner=missing)
    assert result["ok"] is False
    assert "not found" in result["error"]
