"""MCP server — messaging bridges Telegram/Signal isolated opt-in."""

from __future__ import annotations

import os
import pathlib

from shesh_audit.mcp_guard import GuardedMCP as FastMCP
from shesh_secrets import resolve as _resolve_secret

mcp = FastMCP("shesh-messaging")

BRIDGE_DIR = pathlib.Path.home() / ".config/shesh/messaging"

def _is_enabled(bridge: str) -> bool:
    flag = BRIDGE_DIR / f"{bridge}.enabled"
    return flag.exists()

@mcp.tool()
def list_bridges() -> dict:
    """List messaging bridges and whether enabled."""
    return {
        "telegram": {"enabled": _is_enabled("telegram"), "needs": "TELEGRAM_BOT_TOKEN via shesh-secrets"},
        "signal": {"enabled": _is_enabled("signal"), "needs": "signal-cli + SIGNAL account"},
        "note": ("Bridges are isolated opt-in; create flag file "
                 "~/.config/shesh/messaging/{telegram,signal}.enabled to enable"),
    }

def _get_token() -> str | None:
    """TELEGRAM_BOT_TOKEN resolved via a shesh-secrets reference.

    Defaults to env:TELEGRAM_BOT_TOKEN; set SHESH_TELEGRAM_TOKEN_REF to any
    shesh-secrets reference (env:/gopass:/keepassxc:/file:) to source the
    token from an external secret store instead.
    """
    return _resolve_secret(os.environ.get("SHESH_TELEGRAM_TOKEN_REF",
                                          "env:TELEGRAM_BOT_TOKEN"))


class TelegramError(RuntimeError):
    """Base for Telegram Bot API failures."""


class TelegramAPIError(TelegramError):
    """The Bot API answered with an HTTP error."""

    def __init__(self, code: int, detail: str) -> None:
        self.code = code
        super().__init__(f"telegram HTTP {code}: {detail}")


class TelegramRequestError(TelegramError):
    """The Bot API could not be reached or its reply was unreadable."""

    def __init__(self, cause: BaseException) -> None:
        super().__init__(f"telegram request failed: {cause}")


def _telegram_api(token: str, method: str, payload: dict, timeout: int = 10) -> dict:
    """Call the Telegram Bot API. The token only ever lives in the URL path
    of an in-memory request — never in logs, errors, or the return value."""
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - http(s) scheme, config-driven URL
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # with-statement: an HTTPError is a live socket — close it even if the
        # error body cannot be read (see the same leak fixed in shesh-health).
        with exc as e:
            detail = e.read().decode(errors="replace")[:200]
        raise TelegramAPIError(exc.code, detail) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TelegramRequestError(exc) from exc


@mcp.tool()
def send_telegram(chat_id: str, message: str) -> dict:
    """Send a real Telegram message via the Bot API.

    Requires the bridge flag and TELEGRAM_BOT_TOKEN (shesh-secrets or env).
    """
    if not _is_enabled("telegram"):
        return {"ok": False, "error": "telegram bridge not enabled — create ~/.config/shesh/messaging/telegram.enabled"}
    token = _get_token()
    if not token:
        return {
            "ok": False,
            "error": "TELEGRAM_BOT_TOKEN not found (shesh-secrets env:TELEGRAM_BOT_TOKEN or environment)",
        }
    try:
        resp = _telegram_api(token, "sendMessage", {"chat_id": chat_id, "text": message})
    except TelegramError as exc:
        return {"ok": False, "error": str(exc)}
    result = resp.get("result", {})
    return {
        "ok": bool(resp.get("ok")),
        "chat_id": chat_id,
        "message_id": result.get("message_id"),
        "date": result.get("date"),
    }


@mcp.tool()
def read_telegram(offset: int = 0, limit: int = 20, timeout: int = 0) -> dict:
    """Read incoming Telegram updates via getUpdates (a send-only bridge is
    half a bridge — this completes the loop).

    Callers track the offset themselves: pass max(update_id)+1 from the last
    batch to acknowledge. timeout>0 long-polls. Token handling is identical
    to send_telegram: in-memory only, never logged.
    """
    if not _is_enabled("telegram"):
        return {"ok": False, "error": "telegram bridge not enabled — create ~/.config/shesh/messaging/telegram.enabled"}
    token = _get_token()
    if not token:
        return {
            "ok": False,
            "error": "TELEGRAM_BOT_TOKEN not found (shesh-secrets env:TELEGRAM_BOT_TOKEN or environment)",
        }
    limit = max(1, min(int(limit), 100))
    timeout = max(0, min(int(timeout), 60))
    try:
        resp = _telegram_api(token, "getUpdates",
                             {"offset": int(offset), "limit": limit, "timeout": timeout},
                             timeout=timeout + 10)
    except TelegramError as exc:
        return {"ok": False, "error": str(exc)}
    messages = []
    for upd in resp.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or {}
        messages.append({
            "update_id": upd.get("update_id"),
            "chat_id": (msg.get("chat") or {}).get("id"),
            "from": (msg.get("from") or {}).get("username"),
            "text": msg.get("text", ""),
            "date": msg.get("date"),
        })
    next_offset = max((m["update_id"] for m in messages), default=None)
    return {
        "ok": bool(resp.get("ok")),
        "count": len(messages),
        "messages": messages,
        "next_offset": (next_offset + 1) if next_offset is not None else int(offset),
    }


@mcp.tool()
def telegram_status() -> dict:
    """Connectivity + identity probe via getMe. Answers 'is the token valid
    and the API reachable' without exposing anything secret."""
    if not _is_enabled("telegram"):
        return {"ok": False, "error": "telegram bridge not enabled"}
    token = _get_token()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not found"}
    try:
        resp = _telegram_api(token, "getMe", {})
    except TelegramError as exc:
        return {"ok": False, "error": str(exc)}
    me = resp.get("result", {})
    return {"ok": bool(resp.get("ok")), "bot_id": me.get("id"),
            "username": me.get("username"), "can_read": me.get("can_read_all_group_messages", False)}


@mcp.tool()
def send_signal(recipient: str, message: str) -> dict:
    """Send a real Signal message via signal-cli (must be installed+registered)."""
    if not _is_enabled("signal"):
        return {"ok": False, "error": "signal bridge not enabled — create ~/.config/shesh/messaging/signal.enabled"}
    import shutil
    import subprocess

    cli = shutil.which("signal-cli")
    if not cli:
        return {"ok": False, "error": "signal-cli not installed"}
    account = _get_signal_account()
    if not account:
        return {"ok": False, "error": "SIGNAL_ACCOUNT not configured (shesh-secrets env:SIGNAL_ACCOUNT or environment)"}
    try:
        proc = subprocess.run(
            [cli, "-a", account, "send", "-m", message, recipient],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": f"signal-cli failed: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "error": f"signal-cli exit {proc.returncode}: {proc.stderr.strip()[:200]}"}
    return {"ok": True, "recipient": recipient, "sent": True}


def _get_signal_account() -> str | None:
    """SIGNAL_ACCOUNT resolved via a shesh-secrets reference.

    Defaults to env:SIGNAL_ACCOUNT; override with SHESH_SIGNAL_ACCOUNT_REF.
    """
    return _resolve_secret(os.environ.get("SHESH_SIGNAL_ACCOUNT_REF",
                                          "env:SIGNAL_ACCOUNT"))

@mcp.tool()
def enable_bridge(bridge: str) -> dict:
    """Enable a bridge by creating flag file (requires user confirmation in real use)."""
    if bridge not in ("telegram", "signal"):
        return {"ok": False, "error": "unknown bridge, use telegram or signal"}
    BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    flag = BRIDGE_DIR / f"{bridge}.enabled"
    flag.write_text("enabled\n")
    return {"ok": True, "bridge": bridge, "flag": str(flag)}

@mcp.tool()
def disable_bridge(bridge: str) -> dict:
    """Disable a bridge."""
    flag = BRIDGE_DIR / f"{bridge}.enabled"
    if flag.exists():
        flag.unlink()
    return {"ok": True, "bridge": bridge, "disabled": True}

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
