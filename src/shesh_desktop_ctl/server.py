#!/usr/bin/env python3
"""Shesh MCP server: Bluetooth, networking, brightness, clipboard, session.

Closes the highest-value gaps recorded in shesh-skills/GAPS.md. Every call
passes the audit guard, so a destructive action is policy-checked and logged
like any other.

Licence: GPL-3.0-or-later
"""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from . import automation as auto
from . import devices as d
from . import display as disp
from . import documents as docs

mcp = _MCP("shesh-desktop-ctl")


# ── Bluetooth ───────────────────────────────────────────────────────────────

@mcp.tool()
def bluetooth_status() -> dict:
    """Report whether the Bluetooth adapter is powered and scanning."""
    return d.bluetooth_status()


@mcp.tool()
def bluetooth_power(on: bool) -> dict:
    """Turn the Bluetooth adapter on or off."""
    return d.bluetooth_power(on)


@mcp.tool()
def bluetooth_devices(paired_only: bool = True) -> dict:
    """List Bluetooth devices, paired ones by default."""
    return d.bluetooth_devices(paired_only)


@mcp.tool()
def bluetooth_connect(mac: str) -> dict:
    """Connect a paired Bluetooth device by MAC address."""
    return d.bluetooth_connect(mac)


@mcp.tool()
def bluetooth_disconnect(mac: str) -> dict:
    """Disconnect a Bluetooth device by MAC address."""
    return d.bluetooth_disconnect(mac)


# ── Networking ──────────────────────────────────────────────────────────────

@mcp.tool()
def network_status() -> dict:
    """Report the state of every network device."""
    return d.network_status()


@mcp.tool()
def wifi_list() -> dict:
    """List visible Wi-Fi networks, strongest signal first."""
    return d.wifi_list()


@mcp.tool()
def wifi_connect(ssid: str, password: str | None = None) -> dict:
    """Join a Wi-Fi network.

    A password given here appears in the process table. Prefer a saved profile,
    or resolve the secret through shesh-secrets.
    """
    return d.wifi_connect(ssid, password)


@mcp.tool()
def network_set_enabled(on: bool) -> dict:
    """Enable or disable all networking, equivalent to airplane mode."""
    return d.network_set_enabled(on)


# ── Brightness ──────────────────────────────────────────────────────────────

@mcp.tool()
def brightness_get() -> dict:
    """Report screen brightness as a percentage."""
    return d.brightness_get()


@mcp.tool()
def brightness_set(percent: int) -> dict:
    """Set screen brightness. Clamped to a floor of 1 so the panel stays visible."""
    return d.brightness_set(percent)


# ── Clipboard ───────────────────────────────────────────────────────────────

@mcp.tool()
def clipboard_get() -> dict:
    """Read the clipboard.

    The clipboard may hold a password the user copied moments ago. Do not echo
    the value into a log, a note, or a message.
    """
    return d.clipboard_get()


@mcp.tool()
def clipboard_set(text: str) -> dict:
    """Replace the clipboard contents. The previous value is not recoverable."""
    return d.clipboard_set(text)


# ── Session ─────────────────────────────────────────────────────────────────

@mcp.tool()
def session_action(action: str, confirm: bool = False) -> dict:
    """Lock, suspend, hibernate, log out, reboot, or power off.

    Locking is immediate. Every other action ends the session or the machine
    and requires confirm=True, so unsaved work is not lost to a misheard
    instruction.
    """
    return d.session_action(action, confirm)


@mcp.tool()
def idle_inhibit_status() -> dict:
    """List what is currently preventing idle, sleep, or shutdown."""
    return d.idle_inhibit_status()


# ── Services ────────────────────────────────────────────────────────────────

@mcp.tool()
def service_status(unit: str, user: bool = True) -> dict:
    """Report whether a systemd unit is active and enabled."""
    return d.service_status(unit, user)


@mcp.tool()
def service_list_failed(user: bool = True) -> dict:
    """List failed systemd units."""
    return d.service_list_failed(user)


@mcp.tool()
def service_restart(unit: str, user: bool = True, confirm: bool = False) -> dict:
    """Restart a systemd unit. Requires confirm=True; a restart interrupts work."""
    return d.service_restart(unit, user, confirm)


# ── Notifications ───────────────────────────────────────────────────────────

@mcp.tool()
def notify(summary: str, body: str = "", urgency: str = "normal") -> dict:
    """Send a desktop notification."""
    return d.notify(summary, body, urgency)


# ── Display and monitors ────────────────────────────────────────────────────

@mcp.tool()
def list_monitors() -> dict:
    """List monitors with their resolution, refresh rate, scale, and modes."""
    return disp.list_monitors()


@mcp.tool()
def set_monitor_mode(name: str, width: int, height: int,
                     refresh: float | None = None, confirm: bool = False) -> dict:
    """Change resolution and refresh rate.

    Checked against the modes the monitor advertises, and the previous mode is
    returned so it can be restored. Requires confirm=True: an unsupported mode
    can leave the screen unreadable.
    """
    return disp.set_mode(name, width, height, refresh, confirm)


@mcp.tool()
def set_monitor_scale(name: str, scale: float, confirm: bool = False) -> dict:
    """Set fractional scaling between 0.5 and 3.0. Requires confirm=True."""
    return disp.set_scale(name, scale, confirm)


@mcp.tool()
def set_monitor_enabled(name: str, on: bool, confirm: bool = False) -> dict:
    """Enable or disable an output. Disabling the only active output is refused."""
    return disp.set_enabled(name, on, confirm)


# ── Desktop automation (adopted upstream, ADR-0020) ─────────────────────────

@mcp.tool()
def automation_doctor() -> dict:
    """Report whether desktop automation is usable on this machine."""
    return auto.doctor()


@mcp.tool()
def automation_call(tool: str, arguments: dict | None = None,
                    confirm: bool = False) -> dict:
    """Invoke a computer-use-linux tool through the policy guard.

    Reading the screen is permitted freely. Anything that clicks, types, or
    moves a window requires confirm=True: an agent driving the pointer can do
    anything the operator can, and a misread instruction is not recoverable.
    """
    return auto.call(tool, arguments, confirm=confirm)


# ── Documents (sandboxed) ───────────────────────────────────────────────────

@mcp.tool()
def document_to_markdown(path: str) -> dict:
    """Convert a document to Markdown inside a network-isolated container.

    Document parsers are a large attack surface, so nothing is parsed in this
    process. The file is bound read-only into a throwaway container.
    """
    return docs.to_markdown(path)


@mcp.tool()
def document_extract_text(path: str) -> dict:
    """Extract plain text from a document, for search or summarising."""
    return docs.extract_text(path)


@mcp.tool()
def document_inspect(path: str) -> dict:
    """Report page count, title, and encryption without parsing in-process."""
    return docs.inspect(path)


@mcp.tool()
def document_convert(path: str, to: str, out: str | None = None,
                     confirm: bool = False) -> dict:
    """Convert a document to another format. Requires confirm=True to write."""
    return docs.convert(path, to, out, confirm)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
