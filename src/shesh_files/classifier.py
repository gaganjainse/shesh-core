#!/usr/bin/env python3
"""Smart-organizer classifier.

Reads file-event JSON lines from stdin (as emitted by sm-watcher), classifies
each file (deterministic rules first, optional local LLM for unknowns), and
writes decision JSON lines to stdout.

License: GPL-3.0   See docs/SHESH/05_SMART_ORGANIZER_V2.md
"""
from __future__ import annotations

import contextlib
import json
import mimetypes
import os
import pathlib
import re
import sys
import traceback
import urllib.request

HOME = pathlib.Path(os.path.expanduser("~"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "")
LLM_MODEL = os.environ.get("SHESH_CLASSIFIER_MODEL", "phi4-mini")
# Set SHESH_NO_LLM=1 to disable LLM calls (fully offline/deterministic).
NO_LLM = os.environ.get("SHESH_NO_LLM") == "1"

# extension -> destination (relative to HOME)
EXT_MAP: dict[str, str] = {
    # documents
    ".pdf": "Documents/Reference", ".doc": "Documents", ".docx": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".csv": "Documents",
    ".ppt": "Documents", ".pptx": "Documents", ".odt": "Documents",
    ".epub": "Documents/Reference", ".md": "Notes", ".txt": "Documents",
    # media
    ".mp4": "Media/Videos", ".mkv": "Media/Videos", ".mov": "Media/Videos",
    ".webm": "Media/Videos", ".avi": "Media/Videos",
    ".mp3": "Media/Music", ".flac": "Media/Music", ".wav": "Media/Music",
    ".ogg": "Media/Music", ".m4a": "Media/Music",
    ".jpg": "Media/Images", ".jpeg": "Media/Images", ".png": "Media/Images",
    ".gif": "Media/Images", ".webp": "Media/Images", ".heic": "Media/Images",
    ".svg": "Media/Design", ".raw": "Media/Images",
    ".psd": "Media/Design", ".xcf": "Media/Design", ".blend": "Media/Design",
    # code-ish
    ".py": "Projects/labs", ".rs": "Projects/labs", ".js": "Projects/labs",
    ".ts": "Projects/labs", ".sh": "Projects/labs", ".go": "Projects/labs",
    # archives / installers
    ".zip": "Downloads/Archives", ".tar": "Downloads/Archives",
    ".gz": "Downloads/Archives", ".bz2": "Downloads/Archives",
    ".xz": "Downloads/Archives", ".zst": "Downloads/Archives",
    ".7z": "Downloads/Archives", ".rar": "Downloads/Archives",
    ".AppImage": "Downloads/Installers", ".deb": "Downloads/Installers",
    ".rpm": "Downloads/Installers", ".iso": "Downloads/Archives",
    # AI
    ".gguf": "AI/Models", ".safetensors": "AI/Models", ".pt": "AI/Models",
    ".onnx": "AI/Models", ".jsonl": "AI/Datasets", ".parquet": "AI/Datasets",
}

# name regex -> destination (higher signal than extension)
NAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)invoice|receipt|bill|statement"), "Documents/Personal/Finance"),
    (re.compile(r"(?i)resume|\bcv\b|curriculum"), "Documents/Personal"),
    (re.compile(r"(?i)screenshot|screen.?shot|Screenshot from"), "Media/Screenshots"),
    (re.compile(r"(?i)wallpaper|wallhaven"), "Media/Wallpapers"),
    (re.compile(r"(?i)^(IMG|VID|DSC)[_-]"), "Media/Camera"),
    (re.compile(r"(?i)setup|installer"), "Downloads/Installers"),
]


def decide(path: str) -> dict:
    # pathlib ops are pure (no I/O): .name/.suffixes cannot fail. Anything
    # invalid in `path` raises at Path() construction — loudly, which is correct.
    p = pathlib.Path(path)
    name = p.name

    # 1. name patterns
    for rx, dest in NAME_PATTERNS:
        if rx.search(name):
            return {"src": str(p), "dest": str(HOME / dest),
                    "method": "rule", "conf": 0.95}

    # 2. double extension (.tar.gz, .pkg.tar.zst) then single
    double = "".join(p.suffixes[-2:]).lower()
    if double in EXT_MAP:
        return {"src": str(p), "dest": str(HOME / EXT_MAP[double]),
                "method": "rule", "conf": 0.85}
    if p.suffix.lower() in EXT_MAP:
        return {"src": str(p), "dest": str(HOME / EXT_MAP[p.suffix.lower()]),
                "method": "rule", "conf": 0.8}

    # 3. MIME fallback for media
    mime, _ = mimetypes.guess_type(str(p))
    if mime:
        kind = mime.split("/", 1)[0]
        folders = {"image": "Media/Images", "video": "Media/Videos",
                   "audio": "Media/Music", "text": "Documents"}
        if kind in folders:
            return {"src": str(p), "dest": str(HOME / folders[kind]),
                    "method": "mime", "conf": 0.6}

    # 4. LLM tiebreaker (optional, bounded)
    if not NO_LLM:
        llm = _llm(p, mime)
        if llm:
            return llm

    return {"src": str(p), "dest": str(HOME / "Documents/Inbox"),
            "method": "fallback", "conf": 0.2}


def _llm(p: pathlib.Path, mime: str | None) -> dict | None:
    size_mb = 0.0
    with contextlib.suppress(OSError):
        size_mb = p.stat().st_size / 1_000_000
    prompt = (
        "Classify this file into ONE destination folder relative to home. "
        "Choose from: Documents/Reference, Documents/Personal/Finance, "
        "Media/Images, Media/Videos, Media/Music, Downloads/Installers, "
        "Downloads/Archives, Projects/labs, AI/Models, AI/Datasets, Documents/Inbox.\n"
        f"File: {p.name}\nMIME: {mime}\nSizeMB: {size_mb:.1f}\n"
        'Reply with ONLY JSON: {"dest":"<relative>","conf":0.0-1.0}'
    )
    payload = json.dumps({
        "model": LLM_MODEL, "prompt": prompt, "stream": False, "format": "json",
    }).encode()
    try:
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["X-API-Key"] = OLLAMA_API_KEY
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 - http(s) scheme, config-driven URL
            data = json.loads(json.loads(r.read()).get("response", "{}"))
        dest = str(HOME / data["dest"])
        return {"src": str(p), "dest": dest, "method": "llm",
                "conf": float(data.get("conf", 0.4))}
    except (OSError, ValueError, KeyError) as e:  # offline/malformed -> deterministic fallback
        # URLError/TimeoutError are OSErrors; bad JSON and missing keys are
        # ValueError/KeyError. The fallback is announced on stderr, never silent.
        print(f"# llm unavailable: {e}", file=sys.stderr)
        return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            path = ev.get("path")
            if not path:
                continue
            print(json.dumps(decide(path)), flush=True)
        except Exception as e:  # noqa: BLE001
            # Daemon boundary: one malformed event must not kill the stream
            # processor. Loud, not silent: full traceback goes to stderr.
            print(json.dumps({"error": f"{type(e).__name__}: {e}",
                              "traceback": traceback.format_exc(limit=5)}),
                  file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
