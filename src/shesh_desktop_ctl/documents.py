"""Document conversion and extraction, executed in a sandbox.

Closes the document-handling gap in GAPS.md. The anthropics/skills document
skills assume a code-execution sandbox; the fleet has one in shesh-containers,
but its runner could not mount a file, so a document could never reach it.

This adds the missing piece: a read-only bind of the input file into a
throwaway, network-isolated container. Document parsers are a large attack
surface — a malformed PDF is a classic exploit vector — so nothing here parses
in the agent's own process.

Backed by pandoc, poppler, and LibreOffice inside the container image, not by
new Python dependencies in the fleet.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Bigger than any document the operator is likely to convert by hand, small
# enough that a runaway job cannot fill the disk.
MAX_INPUT_BYTES = 64 * 1024 * 1024
TIMEOUT = 120
IMAGE = os.environ.get("SHESH_DOC_IMAGE", "docker.io/pandoc/extra:latest")

READABLE = {".pdf", ".docx", ".doc", ".odt", ".rtf", ".epub", ".html", ".htm",
            ".md", ".markdown", ".txt", ".csv", ".tsv", ".xlsx", ".ods",
            ".pptx", ".odp", ".tex", ".rst", ".org"}
WRITABLE = {"markdown", "gfm", "html", "plain", "docx", "odt", "pdf", "latex",
            "rst", "org", "epub", "json", "csv"}


@dataclass(frozen=True)
class Result:
    stdout: str
    stderr: str
    code: int

    @property
    def ok(self) -> bool:
        return self.code == 0


Runner = Callable[..., Result]


def run(cmd: list[str], *, timeout: int = TIMEOUT) -> Result:
    if not shutil.which(cmd[0]):
        return Result("", f"{cmd[0]} is not installed", 127)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return Result(p.stdout.strip(), p.stderr.strip(), p.returncode)
    except subprocess.TimeoutExpired:
        return Result("", f"timeout after {timeout}s", 124)
    except OSError as exc:
        return Result("", str(exc), 1)


def engine(which: Callable[[str], str | None] = shutil.which) -> str | None:
    for e in ("podman", "docker"):
        if which(e):
            return e
    return None


def _validate(path: str) -> tuple[Path | None, dict | None]:
    """Resolve and check an input path before it reaches a container."""
    if not path or not isinstance(path, str):
        return None, {"ok": False, "error": "no path given"}
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return None, {"ok": False, "error": f"not a file: {p}"}
    if p.suffix.lower() not in READABLE:
        return None, {"ok": False, "error": f"unsupported type: {p.suffix}",
                      "supported": sorted(READABLE)}
    size = p.stat().st_size
    if size > MAX_INPUT_BYTES:
        return None, {"ok": False,
                      "error": f"{size} bytes exceeds the {MAX_INPUT_BYTES} limit"}
    # A protected path must not be readable through a conversion tool.
    protected = ("/.ssh/", "/.gnupg/", "/Vaults/", "/Documents/Job/")
    if any(seg in str(p) for seg in protected):
        return None, {"ok": False,
                      "error": "refusing to read a protected path"}
    return p, None


def _sandbox(argv: list[str], mount: Path, *, runner: Runner,
             which: Callable[[str], str | None]) -> Result:
    """Run argv in a throwaway container with the file bound read-only."""
    eng = engine(which)
    if eng is None:
        return Result("", "no container engine (podman or docker) available", 127)
    return runner([
        eng, "run", "--rm", "-i",
        "--network=none",          # a document never needs the network
        "--cap-drop=ALL",
        "--pids-limit=128",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "-v", f"{mount}:/in/{mount.name}:ro,Z",
        "-w", "/in",
        IMAGE, *argv,
    ], timeout=TIMEOUT)


def to_markdown(path: str, runner: Runner = run,
                which: Callable[[str], str | None] = shutil.which) -> dict:
    """Convert a document to Markdown inside the sandbox."""
    p, err = _validate(path)
    if err:
        return err
    r = _sandbox(["pandoc", "-t", "gfm", "--wrap=none", f"/in/{p.name}"],
                 p, runner=runner, which=which)
    if not r.ok:
        return {"ok": False, "error": r.stderr or r.stdout or "conversion failed"}
    return {"ok": True, "source": str(p), "format": "gfm", "text": r.stdout}


def convert(path: str, to: str, out: str | None = None,
            confirm: bool = False, runner: Runner = run,
            which: Callable[[str], str | None] = shutil.which) -> dict:
    """Convert a document to another format.

    Writing requires confirmation: conversion can overwrite an existing file,
    and the output is produced by a parser the operator has not inspected.
    """
    p, err = _validate(path)
    if err:
        return err
    if to not in WRITABLE:
        return {"ok": False, "error": f"unsupported target: {to}",
                "supported": sorted(WRITABLE)}

    dest = Path(out).expanduser().resolve() if out else p.with_suffix(f".{to}")
    if dest.exists() and not confirm:
        return {"ok": False, "confirm_required": True, "output": str(dest),
                "error": f"{dest} exists and would be overwritten; confirm=True"}
    if not confirm:
        return {"ok": False, "confirm_required": True, "output": str(dest),
                "error": "conversion writes a file; call again with confirm=True"}

    # The image has no shell, so the converted document comes back on stdout
    # and is written here rather than inside the container.
    r = _sandbox(["pandoc", "-t", to, f"/in/{p.name}"], p,
                 runner=runner, which=which)
    if not r.ok:
        return {"ok": False, "error": r.stderr or "conversion failed"}
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(r.stdout, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"could not write {dest}: {exc}"}
    return {"ok": True, "source": str(p), "output": str(dest), "format": to}


def extract_text(path: str, runner: Runner = run,
                 which: Callable[[str], str | None] = shutil.which) -> dict:
    """Extract plain text, for search or summarising."""
    p, err = _validate(path)
    if err:
        return err
    argv = (["pdftotext", "-layout", f"/in/{p.name}", "-"]
            if p.suffix.lower() == ".pdf"
            else ["pandoc", "-t", "plain", "--wrap=none", f"/in/{p.name}"])
    r = _sandbox(argv, p, runner=runner, which=which)
    if not r.ok:
        return {"ok": False, "error": r.stderr or "extraction failed"}
    text = r.stdout
    return {"ok": True, "source": str(p), "characters": len(text),
            "words": len(text.split()), "text": text}


def inspect(path: str, runner: Runner = run,
            which: Callable[[str], str | None] = shutil.which) -> dict:
    """Report what a document is without parsing it in this process."""
    p, err = _validate(path)
    if err:
        return err
    info: dict = {"ok": True, "path": str(p), "suffix": p.suffix.lower(),
                  "bytes": p.stat().st_size}
    if p.suffix.lower() == ".pdf":
        r = _sandbox(["pdfinfo", f"/in/{p.name}"], p, runner=runner, which=which)
        if r.ok:
            for line in r.stdout.splitlines():
                m = re.match(r"^(Pages|Title|Encrypted|Page size):\s*(.+)$", line)
                if m:
                    info[m.group(1).lower().replace(" ", "_")] = m.group(2).strip()
    return info
