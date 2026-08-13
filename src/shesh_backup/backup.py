"""Core backup logic (no I/O on the network/restic at import time)."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .runner import Result, run

DATA_DIR = Path.home() / ".local" / "state" / "shesh" / "backup"
_LEGACY = Path.home() / ".local" / "state" / "shesh" / "backup"
if _LEGACY.exists() and not DATA_DIR.exists():
    _LEGACY.rename(DATA_DIR)  # one-shot migration; legacy name is gone


@dataclass
class BackupConfig:
    repo: str = ""
    paths: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    retention_daily: int = 7
    retention_weekly: int = 4
    retention_monthly: int = 6
    min_interval_hours: int = 20   # don't back up more than ~daily


@dataclass
class BackupState:
    last_run: float = 0.0
    last_status: str = "never"
    snapshots: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> BackupState:
        if path.exists():
            return cls(**json.loads(path.read_text()))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))


def should_run(cfg: BackupConfig, state: BackupState, *, now: float | None = None,
               on_ac: bool = True) -> tuple[bool, str]:
    """Decide whether a backup should run now (policy gate)."""
    if not cfg.repo or not cfg.paths:
        return False, "not configured"
    if not on_ac:
        return False, "not on AC power"
    now = now if now is not None else time.time()
    if now - state.last_run < cfg.min_interval_hours * 3600:
        return False, "ran recently"
    return True, "due"


def backup(cfg: BackupConfig, state: BackupState, state_path: Path,
           *, runner: Callable[..., Result] = run) -> dict:
    """Run restic backup + (optionally) forget/prune. Returns a summary."""
    cmd = ["restic", "-r", cfg.repo, "backup", *cfg.paths]
    for ex in cfg.exclude:
        cmd += ["--exclude", ex]
    r = runner(cmd)
    state.last_run = time.time()
    if not r.ok:
        state.last_status = "failed"
        state.save(state_path)
        return {"ok": False, "error": r.text}

    # Verify the latest snapshot exists.
    snapshots = runner(["restic", "-r", cfg.repo, "snapshots", "--json"])
    try:
        state.snapshots = json.loads(snapshots.stdout or "[]")
    except json.JSONDecodeError:
        state.snapshots = []
    state.last_status = "ok"
    state.save(state_path)
    return {"ok": True, "snapshots": len(state.snapshots), "output": r.text[:500]}


def prune(cfg: BackupConfig, *, runner: Callable[..., Result] = run) -> dict:
    """Apply retention policy. Explicit opt-in (destructive)."""
    cmd = ["restic", "-r", cfg.repo, "forget", "--prune",
           "--keep-daily", str(cfg.retention_daily),
           "--keep-weekly", str(cfg.retention_weekly),
           "--keep-monthly", str(cfg.retention_monthly)]
    r = runner(cmd)
    return {"ok": r.ok, "output": r.text[:500]}
