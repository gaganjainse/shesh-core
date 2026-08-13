"""Secret retrieval with multiple backends.

Secrets are NEVER stored in MCP config files. This module resolves a secret
reference of the form:

  env:VAR_NAME              -> read from environment
  gopass:path/to/secret     -> `gopass show -o path`
  keepassxc:entry           -> `secret-tool lookup ...` (KeePassXC CLI)
  file:/path                -> first line of a 0600 file

The resolver is injectable for tests. Missing secrets return None rather
than raising, so callers can decide policy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

Resolver = Callable[[str], str | None]


def _from_env(key: str) -> str | None:
    v = os.environ.get(key)
    return v if v else None


def _from_gopass(entry: str) -> str | None:
    if not shutil.which("gopass"):
        return None
    try:
        r = subprocess.run(
            ["gopass", "show", "-o", entry],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_keepassxc(entry: str) -> str | None:
    """Use freedesktop secret service (KeePassXC exposes entries this way)."""
    if not shutil.which("secret-tool"):
        return None
    # entry is "attr=value attr2=value2"
    try:
        args = ["secret-tool", "lookup"] + entry.split()
        r = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def _from_file(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        mode = p.stat().st_mode & 0o777
        if mode & 0o077:
            return None  # refuse world/group-readable secret files
        return p.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None


BACKENDS: dict[str, Callable[[str], str | None]] = {
    "env": _from_env,
    "gopass": _from_gopass,
    "keepassxc": _from_keepassxc,
    "file": _from_file,
}


def resolve(ref: str) -> str | None:
    """Resolve a secret reference like 'env:MY_TOKEN'."""
    if ":" not in ref:
        return None
    scheme, _, value = ref.partition(":")
    backend = BACKENDS.get(scheme)
    if backend is None:
        return None
    return backend(value)


def resolve_many(refs: dict[str, str]) -> dict[str, str | None]:
    """Resolve a mapping of name -> secret reference."""
    return {name: (resolve(ref) if is_secret_reference(ref) else ref)
            for name, ref in refs.items()}


def is_secret_reference(value: str) -> bool:
    return isinstance(value, str) and value.split(":", 1)[0] in BACKENDS
