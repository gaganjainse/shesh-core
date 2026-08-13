"""Subprocess wrapper, isolated for tests.

Vendored twin of shesh-skills' runner.py — dedupe policy: tiny stdlib shims
stay vendored per repo (see ecosystem ADR-0018).
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


def run(cmd: list[str], *, timeout: int = 1800) -> Result:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return Result(p.stdout, p.stderr, p.returncode)
    except FileNotFoundError as e:
        return Result("", f"command not found: {cmd[0]} ({e})", 127)
    except subprocess.TimeoutExpired:
        return Result("", f"timeout after {timeout}s", 124)
