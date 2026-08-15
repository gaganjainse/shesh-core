#!/usr/bin/env python3
"""Shesh MCP server: Bluetooth, networking, brightness, clipboard, session.

Closes the highest-value gaps recorded in shesh-skills/GAPS.md. Every call
passes the audit guard, so a destructive action is policy-checked and logged
like any other.

Licence: GPL-3.0-or-later
"""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from . import devices as d

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


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
