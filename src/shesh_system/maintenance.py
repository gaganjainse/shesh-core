"""System maintenance, updates, and health checks for shesh-system.

These are read-only or explicitly-opt-in maintenance operations. They never
auto-update the system (the user controls `-Syu`); they report what is pending
and can clean caches only when asked.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout: {' '.join(cmd)}"


@dataclass
class UpdateStatus:
    available: bool
    count: int
    details: str
    note: str = "review before updating; never auto -Syu"


def check_updates() -> UpdateStatus:
    """Check for pending pacman/AUR updates without applying them."""
    if shutil.which("checkupdates"):
        rc, out = _run(["checkupdates"], timeout=120)
        if rc == 0 and out:
            lines = out.splitlines()
            return UpdateStatus(True, len(lines), out[:2000])
        if rc == 2:
            return UpdateStatus(False, 0, out or "no updates or checkupdates unavailable")
    # Fallback: pacman -Qu (may need sync first; we do NOT sync).
    rc, out = _run(["pacman", "-Qu"], timeout=60)
    if rc == 0 and out:
        return UpdateStatus(True, len(out.splitlines()), out[:2000])
    return UpdateStatus(False, 0, out or "no pending updates")


def cache_size() -> dict:
    """Report sizes of common caches that can be cleaned (without deleting)."""
    targets = {
        "pacman": "/var/cache/pacman/pkg",
        "user_cache": str(Path.home() / ".cache"),
        "journal": "/var/log/journal",
    }
    out: dict[str, int] = {}
    for name, path in targets.items():
        p = Path(path)
        if not p.exists():
            out[name + "_mb"] = 0
            continue
        rc, size_str = _run(["du", "-sm", path])
        if rc == 0:
            try:
                out[name + "_mb"] = int(size_str.split()[0])
            except (IndexError, ValueError):
                out[name + "_mb"] = 0
    return out


def clean_caches(which: str = "user") -> str:
    """Opt-in cache cleanup. which: user|pacman|journal|all."""
    actions: list[str] = []
    if which in ("user", "all"):
        rc, out = _run(["rm", "-rf", str(Path.home() / ".cache" / "*")], timeout=300)
        actions.append(f"user cache: {'cleaned' if rc == 0 else out}")
    if which in ("pacman", "all"):
        rc, out = _run(["sudo", "-n", "pacman", "-Sc", "--noconfirm"], timeout=300)
        actions.append(f"pacman cache: {'cleaned' if rc == 0 else 'needs sudo: ' + out}")
    if which in ("journal", "all"):
        rc, out = _run(["sudo", "-n", "journalctl", "--vacuum-time=7d"], timeout=120)
        actions.append(f"journal: {'vacuumed' if rc == 0 else 'needs sudo: ' + out}")
    return "\n".join(actions)


def health_report() -> dict:
    """High-level health: disk, memory pressure, temperature, failed units."""
    report: dict = {}

    # Disk usage for root and home
    rc, out = _run(["df", "-h", "/"])
    if rc == 0 and out:
        parts = out.splitlines()[-1].split()
        if len(parts) >= 5:
            report["root_disk"] = {"size": parts[1], "used": parts[2],
                                   "avail": parts[3], "use_pct": parts[4]}

    # Failed systemd units
    rc, out = _run(["systemctl", "--failed", "--no-legend"])
    if rc == 0:
        report["failed_units"] = [line.split()[0] for line in out.splitlines()] if out else []

    # Uptime / load
    load = Path("/proc/loadavg")
    if load.exists():
        report["loadavg"] = load.read_text().strip().split()[:3]

    # Temperature via the existing sensor path (reuses get_system_status style).
    temps = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            t = int((zone / "temp").read_text()) // 1000
            if 20 < t < 110:
                temps.append(t)
        except (OSError, ValueError):
            # sysfs entry vanished mid-read or held a non-numeric value.
            continue
    if temps:
        report["max_cpu_temp_c"] = max(temps)

    report["caches"] = cache_size()
    return report
