"""MCP server — media tools: screenshots, recording, wallpaper, audio."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import time

from shesh_audit.mcp_guard import GuardedMCP as FastMCP

mcp = FastMCP("shesh-media")

STATE_DIR = pathlib.Path.home() / ".local" / "state" / "shesh" / "media"
SHOT_DIR = STATE_DIR / "shots"
REC_DIR = STATE_DIR / "recordings"
PID_FILE = STATE_DIR / "recording.pid"


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command, return (returncode, combined output). Never raises."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return out.returncode, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


@mcp.tool()
def screenshot(copy: bool = True, region: bool = False, path: str | None = None) -> dict:
    """Screenshot via grim (full) or grim+slurp (region). Optionally wl-copy."""
    if not shutil.which("grim"):
        return {"ok": False, "error": "grim not installed"}
    geom: list[str] = []
    if region:
        if not shutil.which("slurp"):
            return {"ok": False, "error": "slurp not installed (needed for region)"}
        rc, sel = _run(["slurp"], timeout=60)
        if rc != 0 or not sel:
            return {"ok": False, "error": f"slurp cancelled/failed: {sel}"}
        geom = ["-g", sel]
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = pathlib.Path(path) if path else SHOT_DIR / f"shot-{time.strftime('%Y%m%d-%H%M%S')}.png"
    rc, out = _run(["grim", *geom, str(p)])
    if rc != 0:
        return {"ok": False, "error": out or "grim failed"}
    if copy and shutil.which("wl-copy"):
        with open(p, "rb") as fh:
            subprocess.run(["wl-copy"], stdin=fh, check=False)
    return {"ok": True, "path": str(p)}


@mcp.tool()
def take_screenshot(path: str = "/tmp/shesh_screenshot.png", region: str | None = None) -> dict:
    """Compat alias of screenshot(): explicit path, region as slurp geometry string.

    Strict semantics (same as the new API): hard failure when grim is absent —
    no fabricated success stubs.
    """
    if not shutil.which("grim"):
        return {"ok": False, "error": "grim not installed"}
    cmd = ["grim"]
    if region:
        cmd += ["-g", region]
    cmd.append(path)
    rc, out = _run(cmd)
    if rc != 0:
        return {"ok": False, "error": out or "grim failed"}
    return {"ok": True, "path": path}


@mcp.tool()
def list_sinks() -> dict:
    """List audio sinks via wpctl/pactl.

    Honesty contract: never fabricates sink names. When neither CLI is
    usable the sink list is empty and `ok` is False with the reason;
    `offline` marks that no audio stack answered.
    """
    if not (shutil.which("wpctl") or shutil.which("pactl")):
        return {"ok": False, "sinks": [], "offline": True,
                "reason": "neither wpctl nor pactl installed"}
    rc, out = _run(["wpctl", "status"])
    if rc != 0:
        rc, out = _run(["pactl", "list", "sinks", "short"])
    if rc != 0:
        return {"ok": False, "sinks": [], "offline": True,
                "reason": out or "audio query failed"}
    return {"ok": True, "sinks": out.splitlines()[:20], "offline": False}


@mcp.tool()
def get_volume() -> dict:
    """Read default-sink volume via wpctl. Parses 'Volume: 0.45 [MUTED]'."""
    if not shutil.which("wpctl"):
        return {"ok": False, "error": "wpctl not installed"}
    rc, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if rc != 0:
        return {"ok": False, "error": out or "wpctl get-volume failed"}
    vol = None
    for token in out.split():
        try:
            vol = float(token)
            break
        except ValueError:
            continue  # non-numeric token (e.g. 'Volume:') — skip
    if vol is None:
        return {"ok": False, "error": f"unparseable wpctl output: {out!r}"}
    return {"ok": True, "volume": vol, "muted": "[MUTED]" in out}


@mcp.tool()
def set_volume(volume: float) -> dict:
    """Set default-sink volume (0.0–1.0, hard-capped) via wpctl."""
    if not shutil.which("wpctl"):
        return {"ok": False, "error": "wpctl not installed"}
    try:
        vol = float(volume)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"not a number: {volume!r}"}
    if not 0.0 <= vol <= 1.0:
        return {"ok": False, "error": "volume must be within 0.0–1.0 (capped by policy)"}
    rc, out = _run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{vol:.2f}"])
    if rc != 0:
        return {"ok": False, "error": out or "wpctl set-volume failed"}
    return {"ok": True, "volume": vol}


@mcp.tool()
def set_wallpaper(path: str, output: str = "") -> dict:
    """Set wallpaper via hyprpaper (hyprctl IPC)."""
    p = pathlib.Path(path)
    if not p.exists():
        return {"ok": False, "error": f"file not found {path}"}
    if not shutil.which("hyprctl"):
        return {"ok": False, "error": "hyprctl not installed"}
    _run(["hyprctl", "hyprpaper", "unload", "all"])
    rc, out = _run(["hyprctl", "hyprpaper", "preload", str(p)])
    if rc != 0:
        return {"ok": False, "error": out or "hyprpaper preload failed"}
    target = f"{output},{p}" if output else f",{p}"
    rc, out = _run(["hyprctl", "hyprpaper", "wallpaper", target])
    if rc != 0:
        return {"ok": False, "error": out or "hyprpaper wallpaper failed"}
    return {"ok": True, "path": str(p)}


@mcp.tool()
def start_recording(path: str | None = None) -> dict:
    """Start screen recording via wf-recorder. Fails if already recording."""
    if PID_FILE.exists():
        return {"ok": False, "error": "already recording"}
    if not shutil.which("wf-recorder"):
        return {"ok": False, "error": "wf-recorder not installed"}
    REC_DIR.mkdir(parents=True, exist_ok=True)
    out = pathlib.Path(path) if path else REC_DIR / f"rec-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
    proc = subprocess.Popen(
        ["wf-recorder", "-f", str(out)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PID_FILE.write_text(f"{proc.pid} {out}")
    return {"ok": True, "pid": proc.pid, "path": str(out)}


@mcp.tool()
def stop_recording() -> dict:
    """Stop the running wf-recorder (SIGINT for clean finalize)."""
    if not PID_FILE.exists():
        return {"ok": False, "error": "not recording"}
    pid = PID_FILE.read_text().split()[0]
    PID_FILE.unlink()
    rc, out = _run(["kill", "-INT", pid])
    if rc != 0:
        return {"ok": False, "error": out or f"could not stop pid {pid}"}
    return {"ok": True, "pid": int(pid)}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
