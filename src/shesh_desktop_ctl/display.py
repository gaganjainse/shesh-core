"""Display and monitor control.

Closes the display gap recorded in GAPS.md. Reads and writes monitor state
through the compositor's own control interface rather than a new dependency:
hyprctl on Hyprland, wlr-randr on other wlroots compositors.

Resolution, refresh rate, and scale changes can leave a screen unreadable or
blank, and the operator may not be able to see well enough to undo them. Every
mutating call therefore requires explicit confirmation and reports the previous
value so it can be restored.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

TIMEOUT = 15


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


def _fail(r: Result) -> dict:
    return {"ok": False, "error": r.stderr or r.stdout or "command failed"}


def backend(which: Callable[[str], str | None] = shutil.which) -> str | None:
    """Pick the control interface available on this machine."""
    if which("hyprctl"):
        return "hyprctl"
    if which("wlr-randr"):
        return "wlr-randr"
    return None


# ── reading ─────────────────────────────────────────────────────────────────

def list_monitors(runner: Runner = run,
                  which: Callable[[str], str | None] = shutil.which) -> dict:
    """Report every connected monitor with its current and available modes."""
    be = backend(which)
    if be is None:
        return {"ok": False,
                "error": "no display control available",
                "remedy": "install hyprctl (Hyprland) or wlr-randr"}

    if be == "hyprctl":
        r = runner(["hyprctl", "-j", "monitors"])
        if not r.ok:
            return _fail(r)
        try:
            raw = json.loads(r.stdout or "[]")
        except json.JSONDecodeError:
            return {"ok": False, "error": "hyprctl did not return JSON"}
        monitors = [{
            "name": m.get("name"),
            "description": m.get("description"),
            "width": m.get("width"),
            "height": m.get("height"),
            "refresh": round(m.get("refreshRate", 0), 2),
            "scale": m.get("scale"),
            "x": m.get("x"), "y": m.get("y"),
            "transform": m.get("transform"),
            "focused": m.get("focused"),
            "disabled": m.get("disabled"),
            "modes": m.get("availableModes", []),
        } for m in raw]
        return {"ok": True, "backend": be, "monitors": monitors}

    r = runner(["wlr-randr"])
    if not r.ok:
        return _fail(r)
    monitors, current = [], None
    for line in r.stdout.splitlines():
        if not line.startswith((" ", "\t")) and line.strip():
            if current:
                monitors.append(current)
            current = {"name": line.split()[0], "modes": []}
        elif current is not None:
            m = re.search(r"(\d+)x(\d+)\s+px,\s+([\d.]+)\s*Hz", line)
            if m:
                mode = {"width": int(m.group(1)), "height": int(m.group(2)),
                        "refreshRate": float(m.group(3))}
                current["modes"].append(mode)
                if "current" in line:
                    current.update(width=mode["width"], height=mode["height"],
                                   refresh=mode["refreshRate"])
    if current:
        monitors.append(current)
    return {"ok": True, "backend": be, "monitors": monitors}


def _find(name: str, runner: Runner, which) -> dict | None:
    got = list_monitors(runner, which)
    if not got.get("ok"):
        return None
    for m in got["monitors"]:
        if m.get("name") == name:
            return m
    return None


# ── writing ─────────────────────────────────────────────────────────────────

def set_mode(name: str, width: int, height: int, refresh: float | None = None,
             confirm: bool = False, runner: Runner = run,
             which: Callable[[str], str | None] = shutil.which) -> dict:
    """Change resolution and refresh rate.

    An unsupported mode can black the display out. The mode is checked against
    the monitor's advertised list first, and the previous mode is returned so
    it can be restored.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return {"ok": False, "error": f"unsafe monitor name: {name!r}"}
    for v, label in ((width, "width"), (height, "height")):
        if not isinstance(v, int) or v <= 0:
            return {"ok": False, "error": f"{label} must be a positive integer"}

    current = _find(name, runner, which)
    if current is None:
        return {"ok": False, "error": f"no monitor named {name!r}"}

    modes = current.get("modes") or []
    if modes:
        wanted = (width, height)
        available = {(m.get("width"), m.get("height")) for m in modes
                     if isinstance(m, dict)}
        # hyprctl may return modes as "1920x1080@144.00Hz" strings.
        for m in modes:
            if isinstance(m, str):
                mm = re.match(r"(\d+)x(\d+)", m)
                if mm:
                    available.add((int(mm.group(1)), int(mm.group(2))))
        if available and wanted not in available:
            return {"ok": False,
                    "error": f"{width}x{height} is not advertised by {name}",
                    "available": sorted(f"{w}x{h}" for w, h in available if w)}

    previous = {"width": current.get("width"), "height": current.get("height"),
                "refresh": current.get("refresh")}
    if not confirm:
        return {"ok": False, "confirm_required": True, "monitor": name,
                "previous": previous,
                "error": ("changing the mode can leave the screen unreadable; "
                          "call again with confirm=True")}

    be = backend(which)
    if be == "hyprctl":
        spec = f"{name},{width}x{height}"
        spec += f"@{refresh}" if refresh else ""
        spec += f",{current.get('x', 0)}x{current.get('y', 0)},{current.get('scale', 1)}"
        r = runner(["hyprctl", "keyword", "monitor", spec])
    else:
        cmd = ["wlr-randr", "--output", name, "--mode",
               f"{width}x{height}" + (f"@{refresh}Hz" if refresh else "")]
        r = runner(cmd)
    if not r.ok:
        return _fail(r)
    return {"ok": True, "monitor": name, "previous": previous,
            "current": {"width": width, "height": height, "refresh": refresh}}


def set_scale(name: str, scale: float, confirm: bool = False,
              runner: Runner = run,
              which: Callable[[str], str | None] = shutil.which) -> dict:
    """Change fractional scaling. Bounded: extreme values make text unusable."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return {"ok": False, "error": f"unsafe monitor name: {name!r}"}
    if not isinstance(scale, int | float) or not 0.5 <= float(scale) <= 3.0:
        return {"ok": False, "error": "scale must be between 0.5 and 3.0"}

    current = _find(name, runner, which)
    if current is None:
        return {"ok": False, "error": f"no monitor named {name!r}"}
    if not confirm:
        return {"ok": False, "confirm_required": True, "monitor": name,
                "previous": {"scale": current.get("scale")},
                "error": "scaling changes affect every window; confirm=True"}

    if backend(which) == "hyprctl":
        spec = (f"{name},{current.get('width')}x{current.get('height')}"
                f"@{current.get('refresh')},"
                f"{current.get('x', 0)}x{current.get('y', 0)},{scale}")
        r = runner(["hyprctl", "keyword", "monitor", spec])
    else:
        r = runner(["wlr-randr", "--output", name, "--scale", str(scale)])
    if not r.ok:
        return _fail(r)
    return {"ok": True, "monitor": name,
            "previous": {"scale": current.get("scale")}, "current": {"scale": scale}}


def set_enabled(name: str, on: bool, confirm: bool = False,
                runner: Runner = run,
                which: Callable[[str], str | None] = shutil.which) -> dict:
    """Enable or disable an output.

    Disabling the only active monitor leaves no way to see the result, so that
    case is refused outright rather than confirmed.
    """
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name or ""):
        return {"ok": False, "error": f"unsafe monitor name: {name!r}"}

    got = list_monitors(runner, which)
    if not got.get("ok"):
        return got
    active = [m for m in got["monitors"] if not m.get("disabled")]
    if not on and len(active) <= 1 and any(m.get("name") == name for m in active):
        return {"ok": False,
                "error": (f"{name} is the only active output; disabling it "
                          f"would leave no display")}
    if not confirm:
        return {"ok": False, "confirm_required": True, "monitor": name,
                "error": f"{'enabling' if on else 'disabling'} {name} "
                         f"rearranges every window; confirm=True"}

    if backend(which) == "hyprctl":
        spec = f"{name},{'preferred,auto,1' if on else 'disable'}"
        r = runner(["hyprctl", "keyword", "monitor", spec])
    else:
        r = runner(["wlr-randr", "--output", name, "--on" if on else "--off"])
    if not r.ok:
        return _fail(r)
    return {"ok": True, "monitor": name, "enabled": on}
