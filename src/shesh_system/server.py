#!/usr/bin/env python3
"""Shesh MCP server — system control for the MSI Sword 16 HX on CachyOS.

Exposes power/GPU/battery/backup tools to Newelle (and any MCP client) over stdio.
All subprocess calls are in thin wrappers so tests can monkeypatch them without
touching real hardware.

License: GPL-3.0   See docs/SHESH/06_SHESH_AGENT.md
"""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from pathlib import Path

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .maintenance import check_updates, clean_caches, health_report

mcp = _MCP("shesh-system")

# Canonical power profile map.
POWER_PROFILES = {
    "gaming": "performance",
    "performance": "performance",
    "balanced": "balanced",
    "battery": "power-saver",
    "power-saver": "power-saver",
}


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"timeout: {' '.join(cmd)}"


@mcp.tool()
def set_power_profile(mode: str) -> str:
    """Set the power profile. mode: performance/gaming, balanced, battery/power-saver."""
    profile = POWER_PROFILES.get(mode.lower())
    if not profile:
        return f"Unknown mode '{mode}'. Use: performance, balanced, battery."
    out = _run(["powerprofilesctl", "set", profile])
    # Lighten visuals on battery, restore on performance.
    if shutil.which("hyprctl"):
        if profile == "power-saver":
            _run(["hyprctl", "--keyword", "decoration:blur:passes", "1"])
            _run(["hyprctl", "--keyword", "decoration:shadow:enabled", "0"])
        else:
            _run(["hyprctl", "--keyword", "decoration:blur:passes", "3"])
            _run(["hyprctl", "--keyword", "decoration:shadow:enabled", "1"])
    return f"Power profile set to {profile}." + (f" {out}" if out else "")


@mcp.tool()
def get_power_profile() -> str:
    """Return the currently active power profile."""
    return _run(["powerprofilesctl", "get"])


@mcp.tool()
def switch_gpu_mode(mode: str) -> str:
    """Switch GPU/power mode. mode: gaming, battery, balanced (via msi-mux-switcher if present)."""
    # Software side = power profile; full MUX switch requires reboot and msi-mux-switcher.
    base = set_power_profile(mode)
    if shutil.which("msi-mux-switcher"):
        mux = {"gaming": "dgpu", "battery": "igpu", "balanced": "hybrid"}.get(mode.lower())
        if mux:
            base += " Note: full dGPU MUX switch requires reboot; use: sudo msi-mux-switcher " + mux
    return base


@mcp.tool()
def get_system_status() -> dict:
    """Get CPU temp, GPU usage/VRAM, RAM, battery level and state."""
    status: dict = {}

    # NVIDIA GPU
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            text=True, timeout=10,
        ).strip().split(", ")
        status["gpu"] = {
            "temp_c": int(out[0]), "util_pct": int(out[1]),
            "vram_used_mb": int(out[2]), "vram_total_mb": int(out[3]),
            "power_w": float(out[4]),
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        # Missing binary, timeout, non-zero exit, or CSV we could not parse.
        status["gpu"] = {"error": f"nvidia-smi unavailable: {exc}"}

    # CPU temperature: first thermal zone that reports a sane value.
    cpu_temp = -1
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            t = int((zone / "temp").read_text().strip()) // 1000
            if 20 < t < 110:
                cpu_temp = t
                break
        except (OSError, ValueError):
            # Zone disappeared or held a non-numeric value — try the next one.
            continue
    status["cpu_temp_c"] = cpu_temp

    # Memory
    try:
        mem: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, rest = line.partition(":")
            mem[k] = int(rest.strip().split()[0])  # kB
        avail = mem.get("MemAvailable", 0)
        total = mem.get("MemTotal", 0)
        status["ram"] = {
            "total_gb": round(total / 1_048_576, 1),
            "used_gb": round((total - avail) / 1_048_576, 1),
        }
    except (OSError, ValueError) as exc:
        # /proc/meminfo unreadable or unparseable — surface it, never drop it silently.
        status["ram"] = {"error": f"meminfo unavailable: {exc}"}

    # Battery / AC read defensively (files may be absent or unreadable).
    with contextlib.suppress(OSError, ValueError):
        bat = Path("/sys/class/power_supply/BAT0")
        if bat.exists():
            status["battery"] = {
                "percent": int((bat / "capacity").read_text().strip()),
                "state": (bat / "status").read_text().strip(),
            }
    with contextlib.suppress(OSError, ValueError):
        ac = Path("/sys/class/power_supply/AC")
        if ac.exists():
            status["ac_online"] = (ac / "online").read_text().strip() == "1"

    return status


@mcp.tool()
def run_backup(dry_run: bool = False) -> str:
    """Trigger the Shesh/restic backup. dry_run=true previews without changes."""
    script = Path.home() / ".local" / "bin" / "shesh-backup"
    if not script.exists():
        return "Backup script not installed (~/.local/bin/shesh-backup)."
    env = dict(os.environ, DRY_RUN="1" if dry_run else "0")
    r = subprocess.run([str(script)], capture_output=True, text=True, env=env, timeout=1800)
    return (r.stdout + r.stderr).strip()[-4000:] or "backup complete"


@mcp.tool()
def mux_status() -> str:
    """Report the current MSI MUX / GPU mode (needs msi-mux-switcher)."""
    if not shutil.which("msi-mux-switcher"):
        return "msi-mux-switcher not installed"
    return _run(["sudo", "-n", "msi-mux-switcher", "status"])



@mcp.tool()
def check_system_updates() -> dict:
    """Check for pending pacman/AUR updates (read-only; never auto-updates)."""
    s = check_updates()
    return {"available": s.available, "count": s.count, "details": s.details, "note": s.note}


@mcp.tool()
def clean_system_caches(which: str = "user") -> str:
    """Clean caches: which=user|pacman|journal|all (pacman/journal need sudo)."""
    return clean_caches(which)


@mcp.tool()
def system_health() -> dict:
    """Report disk, failed units, load, temperature, and cache sizes."""
    return health_report()


def main() -> None:
    """Entry point for the shesh-system-mcp console script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
