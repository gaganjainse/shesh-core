"""Everyday Shesh tools exposed over MCP.

All functions are plain Python (no global state) so they can be unit-tested
without a running MCP server. The MCP wiring lives in server.py.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .runner import run

HOME = Path(os.path.expanduser("~"))
DEFAULT_VAULT = HOME / "Notes"


# ── Notes / docs ────────────────────────────────────────────────────────────
def append_note(name: str, content: str, vault: str | None = None,
                timestamp: bool = True) -> dict:
    """Append text to a markdown note (creates it if missing)."""
    root = Path(vault or DEFAULT_VAULT)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if not safe.endswith(".md"):
        safe += ".md"
    path = root / safe
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" if timestamp else "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(prefix + content.rstrip() + "\n")
    return {"ok": True, "path": str(path)}


def find_notes(query: str, vault: str | None = None) -> list[str]:
    """Case-insensitive filename search across the notes vault."""
    root = Path(vault or DEFAULT_VAULT)
    if not root.exists():
        return []
    q = query.lower()
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.md") if q in p.name.lower())


def search_notes(query: str, vault: str | None = None) -> list[dict]:
    """Full-text grep across the vault; returns file + matching lines."""
    root = Path(vault or DEFAULT_VAULT)
    if not root.exists():
        return []
    out: list[dict] = []
    for p in root.rglob("*.md"):
        try:
            hits = [ln.strip() for ln in p.read_text(errors="ignore").splitlines()
                    if query.lower() in ln.lower()]
        except OSError:
            continue
        if hits:
            out.append({"file": str(p.relative_to(root)), "matches": hits[:5]})
    return out


# ── Web / search ────────────────────────────────────────────────────────────
def duckduckgo_search(query: str, limit: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo's instant HTML endpoint (no API key)."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Shesh"})  # nosec B310 - https scheme, hardcoded
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001 - network failures are expected
        return [{"error": str(e)}]
    results = []
    # Result links look like: <a class="result__a" href="...">title</a>
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         html, re.S):
        href, title = m.group(1), re.sub(r"<[^>]+", "", m.group(2)).strip()
        # DDG wraps urls in a redirect; unwrap.
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        real = qs.get("uddg", [href])[0]
        results.append({"title": title, "url": urllib.parse.unquote(real)})
        if len(results) >= limit:
            break
    return results


def fetch_url(url: str, max_bytes: int = 200_000) -> dict:
    """Fetch a URL and return text (HTML stripped to rough text).

    Only http/https are permitted — this blocks SSRF-style schemes like
    file://, gopher:// and internal-network protocols (bandit B310).
    """
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in ("http", "https"):
        return {"error": f"scheme {scheme!r} not allowed (http/https only)"}
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Shesh"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(max_bytes).decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", data)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {"url": url, "bytes": len(data), "text": text[:8000]}


# ── Coding ──────────────────────────────────────────────────────────────────
def git_status(path: str = ".") -> str:
    return run(["git", "-C", path, "status", "--short", "--branch"]).text


def git_log(path: str = ".", n: int = 10) -> str:
    return run(["git", "-C", path, "log", f"-n{n}", "--oneline", "--color=never"]).text


def github_view(repo: str) -> dict:
    """View a GitHub repo/issue via gh CLI (read-only; no writes)."""
    r = run(["gh", "repo", "view", repo, "--json",
             "name,description,stargazerCount,url,defaultBranchRef"])
    if not r.ok:
        return {"error": r.text}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"raw": r.text}


# ── Documents ───────────────────────────────────────────────────────────────
def convert_to_markdown(file_path: str) -> str:
    """Convert a document to Markdown using pandoc (if installed)."""
    r = run(["pandoc", "-t", "gfm", file_path], timeout=120)
    if not r.ok and "not found" in r.stderr:
        return "pandoc is not installed (install it for document conversion)"
    return r.stdout or r.stderr


# ── Scheduling ──────────────────────────────────────────────────────────────
def remind(in_minutes: int, text: str) -> dict:
    """Schedule a one-shot desktop notification via `at` or a background sleep."""
    safe = text.replace("'", "'\\''")
    # Prefer `at` if available; else a detached sleep+notify-send.
    if run(["bash", "-c", "command -v at"]).ok:
        cmd = f"echo \"notify-send Shesh '{safe}'\" | at now + {in_minutes} min"
        r = run(["bash", "-c", cmd])
    else:
        r = run(["bash", "-c",
                 f"( sleep {in_minutes * 60}; notify-send Shesh '{safe}' ) & disown"])
    return {"ok": r.ok, "in_minutes": in_minutes, "detail": r.text}
