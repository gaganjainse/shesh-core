"""MCP server exposing shesh-backup."""
from __future__ import annotations

import json

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .backup import (
    DATA_DIR,
    BackupConfig,
    BackupState,
    backup,
    prune,
    should_run,
)
from .runner import run as _run

mcp = _MCP("shesh-backup")

STATE_PATH = DATA_DIR / "state.json"
CONFIG_PATH = DATA_DIR / "config.json"


def _load_config() -> BackupConfig:
    if CONFIG_PATH.exists():
        return BackupConfig(**json.loads(CONFIG_PATH.read_text()))
    return BackupConfig()


def _load_state() -> BackupState:
    return BackupState.load(STATE_PATH)


@mcp.tool()
def configure(repo: str, paths: list[str], exclude: list[str] | None = None) -> dict:
    """Set the restic repository, paths to back up, and exclusions."""
    cfg = BackupConfig(repo=repo, paths=list(paths), exclude=list(exclude or []))
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg.__dict__, indent=2))
    return {"ok": True, "repo": repo, "paths": paths}


@mcp.tool()
def status() -> dict:
    """Report whether a backup is due and the last result."""
    cfg = _load_config()
    state = _load_state()
    due, reason = should_run(cfg, state)
    return {"due": due, "reason": reason, "last_status": state.last_status,
            "last_run": state.last_run, "snapshots": len(state.snapshots)}


@mcp.tool()
def run_backup() -> dict:
    """Run a backup now (only if due and on AC; respects the schedule)."""
    cfg = _load_config()
    state = _load_state()
    due, reason = should_run(cfg, state)
    if not due:
        return {"ok": False, "skipped": reason}
    return backup(cfg, state, STATE_PATH, runner=_run)


@mcp.tool()
def run_prune() -> dict:
    """Apply retention policy (forget --prune). Explicit/destructive."""
    return prune(_load_config(), runner=_run)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
