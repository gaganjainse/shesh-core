"""Offline tests for secret resolution."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_secrets import (  # noqa: E402
    is_secret_reference,
    resolve,
    resolve_many,
)


def test_env_backend(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "s3cr3t")
    assert resolve("env:MY_TOKEN") == "s3cr3t"


def test_env_missing():
    os.environ.pop("DEFINITELY_NOT_SET", None)
    assert resolve("env:DEFINITELY_NOT_SET") is None


def test_file_backend(tmp_path):
    f = tmp_path / "token"
    f.write_text("abc123\n")
    f.chmod(0o600)
    assert resolve(f"file:{f}") == "abc123"


def test_file_refuses_world_readable(tmp_path):
    f = tmp_path / "token"
    f.write_text("abc")
    f.chmod(0o644)
    assert resolve(f"file:{f}") is None


def test_unknown_scheme():
    assert resolve("bogus:thing") is None


def test_invalid_reference():
    assert not is_secret_reference("plaintext")
    assert is_secret_reference("env:X")


def test_resolve_many(monkeypatch):
    monkeypatch.setenv("A", "1")
    out = resolve_many({"a": "env:A", "b": "literal"})
    assert out == {"a": "1", "b": "literal"}


def test_gopass_uses_cli(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/gopass")

    class FakeProc:
        returncode = 0
        stdout = "secretvalue\n"

    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProc())
    assert resolve("gopass:work/token") == "secretvalue"
