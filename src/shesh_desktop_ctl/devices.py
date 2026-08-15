"""Device and session control: Bluetooth, networking, brightness, clipboard, session.

Pure functions with an injectable runner so every path is testable without the
hardware. Nothing here talks to D-Bus directly; the vendor CLIs (bluetoothctl,
nmcli, brightnessctl, wl-clipboard, loginctl, systemctl) are stable interfaces
and avoid a hard dependency on a Python D-Bus binding.

Every function returns a dict with an "ok" key. A missing tool is reported, not
raised, so an agent gets an actionable message instead of a traceback.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_TIMEOUT = 20


@dataclass(frozen=True)
class Result:
    stdout: str
    stderr: str
    code: int

    @property
    def ok(self) -> bool:
        return self.code == 0


Runner = Callable[..., Result]


def run(cmd: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> Result:
    if not shutil.which(cmd[0]):
        return Result("", f"{cmd[0]} is not installed", 127)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return Result(p.stdout.strip(), p.stderr.strip(), p.returncode)
    except subprocess.TimeoutExpired:
        return Result("", f"timeout after {timeout}s: {' '.join(cmd)}", 124)
    except OSError as exc:
        return Result("", str(exc), 1)


def _fail(r: Result) -> dict:
    return {"ok": False, "error": r.stderr or r.stdout or "command failed"}


# ── Bluetooth ───────────────────────────────────────────────────────────────

def bluetooth_status(runner: Runner = run) -> dict:
    r = runner(["bluetoothctl", "show"])
    if not r.ok:
        return _fail(r)
    powered = re.search(r"Powered:\s*(yes|no)", r.stdout)
    discovering = re.search(r"Discovering:\s*(yes|no)", r.stdout)
    return {
        "ok": True,
        "powered": powered.group(1) == "yes" if powered else None,
        "discovering": discovering.group(1) == "yes" if discovering else None,
    }


def bluetooth_power(on: bool, runner: Runner = run) -> dict:
    r = runner(["bluetoothctl", "power", "on" if on else "off"])
    return {"ok": r.ok, "powered": on} if r.ok else _fail(r)


def bluetooth_devices(paired_only: bool = True, runner: Runner = run) -> dict:
    r = runner(["bluetoothctl", "devices"] + (["Paired"] if paired_only else []))
    if not r.ok:
        return _fail(r)
    devices = []
    for line in r.stdout.splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})\s+(.*)", line.strip(), re.I)
        if m:
            devices.append({"mac": m.group(1), "name": m.group(2)})
    return {"ok": True, "devices": devices}


def bluetooth_connect(mac: str, runner: Runner = run) -> dict:
    if not re.fullmatch(r"[0-9A-Fa-f:]{17}", mac):
        return {"ok": False, "error": f"not a MAC address: {mac!r}"}
    r = runner(["bluetoothctl", "connect", mac], timeout=30)
    ok = r.ok and "successful" in r.stdout.lower()
    return {"ok": ok, "mac": mac, "detail": r.stdout} if ok else _fail(r)


def bluetooth_disconnect(mac: str, runner: Runner = run) -> dict:
    if not re.fullmatch(r"[0-9A-Fa-f:]{17}", mac):
        return {"ok": False, "error": f"not a MAC address: {mac!r}"}
    r = runner(["bluetoothctl", "disconnect", mac])
    return {"ok": r.ok, "mac": mac} if r.ok else _fail(r)


# ── Networking ──────────────────────────────────────────────────────────────

def network_status(runner: Runner = run) -> dict:
    r = runner(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device", "status"])
    if not r.ok:
        return _fail(r)
    devices = []
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3:
            devices.append({"type": parts[0], "state": parts[1],
                            "connection": parts[2] or None})
    return {"ok": True, "devices": devices}


def wifi_list(runner: Runner = run) -> dict:
    r = runner(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
    if not r.ok:
        return _fail(r)
    seen, networks = set(), []
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] and parts[0] not in seen:
            seen.add(parts[0])
            networks.append({
                "ssid": parts[0],
                "signal": int(parts[1]) if parts[1].isdigit() else None,
                "security": parts[2] or "open",
            })
    networks.sort(key=lambda n: n["signal"] or 0, reverse=True)
    return {"ok": True, "networks": networks}


def wifi_connect(ssid: str, password: str | None = None,
                 runner: Runner = run) -> dict:
    """Join a network.

    A password passed here reaches the process table. Prefer a saved
    NetworkManager profile, or resolve the secret through shesh-secrets.
    """
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    r = runner(cmd, timeout=45)
    return {"ok": r.ok, "ssid": ssid} if r.ok else _fail(r)


def network_set_enabled(on: bool, runner: Runner = run) -> dict:
    r = runner(["nmcli", "networking", "on" if on else "off"])
    return {"ok": r.ok, "enabled": on} if r.ok else _fail(r)


# ── Brightness ──────────────────────────────────────────────────────────────

def brightness_get(runner: Runner = run) -> dict:
    cur = runner(["brightnessctl", "get"])
    mx = runner(["brightnessctl", "max"])
    if not (cur.ok and mx.ok):
        return _fail(cur if not cur.ok else mx)
    try:
        c, m = int(cur.stdout), int(mx.stdout)
    except ValueError:
        return {"ok": False, "error": "unparseable brightness"}
    return {"ok": True, "raw": c, "max": m,
            "percent": round(c / m * 100) if m else 0}


def brightness_set(percent: int, runner: Runner = run) -> dict:
    """Set screen brightness.

    Clamped to a floor of 1: setting 0 blanks the panel and the user may not be
    able to see well enough to undo it.
    """
    if not isinstance(percent, int):
        return {"ok": False, "error": "percent must be an integer"}
    percent = max(1, min(100, percent))
    r = runner(["brightnessctl", "set", f"{percent}%"])
    return {"ok": r.ok, "percent": percent} if r.ok else _fail(r)


# ── Clipboard ───────────────────────────────────────────────────────────────

def clipboard_get(runner: Runner = run) -> dict:
    r = runner(["wl-paste", "--no-newline"])
    if not r.ok:
        # An empty clipboard exits non-zero; that is not an error.
        if "empty" in r.stderr.lower():
            return {"ok": True, "text": ""}
        return _fail(r)
    return {"ok": True, "text": r.stdout}


def clipboard_set(text: str, runner: Runner = run) -> dict:
    if not shutil.which("wl-copy"):
        return {"ok": False, "error": "wl-copy is not installed"}
    try:
        p = subprocess.run(["wl-copy"], input=text, text=True,
                           capture_output=True, timeout=DEFAULT_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip() or "wl-copy failed"}
    return {"ok": True, "length": len(text)}


# ── Session ─────────────────────────────────────────────────────────────────

# Locking is safe and reversible. Everything else here ends the session or the
# machine, so it is gated behind an explicit confirm at the server layer.
SESSION_ACTIONS = {
    "lock": (["loginctl", "lock-session"], False),
    "suspend": (["systemctl", "suspend"], True),
    "hibernate": (["systemctl", "hibernate"], True),
    "logout": (["loginctl", "terminate-session", "self"], True),
    "reboot": (["systemctl", "reboot"], True),
    "poweroff": (["systemctl", "poweroff"], True),
}


def session_action(action: str, confirm: bool = False,
                   runner: Runner = run) -> dict:
    if action not in SESSION_ACTIONS:
        return {"ok": False, "error": f"unknown action {action!r}",
                "available": sorted(SESSION_ACTIONS)}
    cmd, destructive = SESSION_ACTIONS[action]
    if destructive and not confirm:
        return {"ok": False, "confirm_required": True, "action": action,
                "error": f"{action} ends the session or powers down the "
                         f"machine; call again with confirm=True"}
    r = runner(cmd)
    return {"ok": r.ok, "action": action} if r.ok else _fail(r)


def idle_inhibit_status(runner: Runner = run) -> dict:
    r = runner(["systemd-inhibit", "--list", "--no-legend"])
    if not r.ok:
        return _fail(r)
    return {"ok": True, "inhibitors": [
        ln.strip() for ln in r.stdout.splitlines() if ln.strip()]}


# ── Services ────────────────────────────────────────────────────────────────

def service_status(unit: str, user: bool = True, runner: Runner = run) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9@._-]+", unit):
        return {"ok": False, "error": f"unsafe unit name: {unit!r}"}
    scope = ["--user"] if user else []
    active = runner(["systemctl", *scope, "is-active", unit])
    enabled = runner(["systemctl", *scope, "is-enabled", unit])
    return {"ok": True, "unit": unit, "scope": "user" if user else "system",
            "active": active.stdout or "unknown",
            "enabled": enabled.stdout or "unknown"}


def service_list_failed(user: bool = True, runner: Runner = run) -> dict:
    scope = ["--user"] if user else []
    r = runner(["systemctl", *scope, "--failed", "--no-legend", "--plain"])
    if not r.ok:
        return _fail(r)
    units = [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()]
    return {"ok": True, "failed": units, "count": len(units)}


def service_restart(unit: str, user: bool = True, confirm: bool = False,
                    runner: Runner = run) -> dict:
    """Restart a unit. Interrupts whatever it is doing, so it needs confirming."""
    if not re.fullmatch(r"[A-Za-z0-9@._-]+", unit):
        return {"ok": False, "error": f"unsafe unit name: {unit!r}"}
    if not confirm:
        return {"ok": False, "confirm_required": True, "unit": unit,
                "error": f"restarting {unit} interrupts it; call again with "
                         f"confirm=True"}
    scope = ["--user"] if user else []
    r = runner(["systemctl", *scope, "restart", unit], timeout=45)
    return {"ok": r.ok, "unit": unit} if r.ok else _fail(r)


# ── Notifications ───────────────────────────────────────────────────────────

def notify(summary: str, body: str = "", urgency: str = "normal",
           runner: Runner = run) -> dict:
    if urgency not in {"low", "normal", "critical"}:
        return {"ok": False, "error": "urgency must be low, normal, or critical"}
    r = runner(["notify-send", "-u", urgency, summary, body])
    return {"ok": r.ok, "summary": summary} if r.ok else _fail(r)
