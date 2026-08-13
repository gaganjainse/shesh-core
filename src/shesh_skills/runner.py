"""Vendored twin of shesh-backup's runner.py (dedupe policy documented in shesh-backup + ADR-0018).
Tiny subprocess wrapper used by every tool.

Centralizing command execution makes the whole server testable: tests patch
`run` to record calls instead of spawning real processes.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def text(self) -> str:
        return (self.stdout + self.stderr).strip()


def run(cmd: list[str], *, timeout: int = 60, input_text: str | None = None) -> Result:
    """Run a command, capturing output. Never raises on non-zero exit."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, input=input_text,
        )
        return Result(p.stdout, p.stderr, p.returncode)
    except FileNotFoundError as e:
        return Result("", f"command not found: {cmd[0]} ({e})", 127)
    except subprocess.TimeoutExpired:
        return Result("", f"timeout after {timeout}s: {' '.join(cmd)}", 124)
