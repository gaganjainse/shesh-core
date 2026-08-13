"""shesh-backup: local, verified restic backups.

Wraps restic with a safe default policy: only run when on AC, respect a daily
schedule written to state, verify snapshots, and never auto-forget/prune without
an explicit flag. The restic binary and repo password are injected via env so
this module has no secrets and is fully testable offline.
"""
from __future__ import annotations

__version__ = "0.1.0"
