"""Tool-description integrity pins — defeats MCP rug pulls and tool poisoning.

Research background (see docs/THREAT_MODEL.md):
- *Tool poisoning* (Invariant Labs, 2025-04): hidden instructions inside a
  tool's description steer the agent while the UI shows something innocuous.
- *Rug pull*: a server changes a tool's description AFTER the user approved
  the tool, upgrading an audited tool into a malicious one without any code
  path re-review.

Defense implemented here (fails LOUD, never silent):
1. Every GuardedMCP tool registration hashes (name, description, signature)
   into a per-server pin file under the shesh state dir.
2. First boot LEARNS pins loudly on stderr. A pin file is then authoritative.
3. Any later registration whose hash differs from the pin raises ToolPinDrift.
   A newly introduced tool name also raises ToolPinDrift until the operator
   explicitly re-pins the server.
4. Descriptions are additionally scanned for poisoning markers (zero-width
   and bidi unicode, embedded HTML comments, instruction-override phrases,
   oversized payloads). Any hit is drift-fatal at registration time.

Intended changes are blessed explicitly:

    python -m shesh_audit.tool_pins --repin <server-name>
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
import unicodedata
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "shesh" / "audit"
PIN_DIR = STATE_DIR / "tool-pins"

OVERRIDE_PHRASES = re.compile(
    r"ignore (all |any |the )?(previous|prior|above) instructions"
    r"|disregard (all |any )?(previous|prior) instructions"
    r"|do not follow (your|the) (system|developer)"
    r"|<\s*system\s*>|<\s*/?\s*instructions?\s*>",
    re.IGNORECASE,
)
MAX_DESCRIPTION = 4000


class ToolPinDrift(RuntimeError):
    """A registered tool no longer matches its integrity pin (rug pull)."""


class ToolPoisoningMarker(ToolPinDrift):
    """A tool description carries a poisoning marker."""


def scan_description(description: str) -> list[str]:
    """Return poisoning findings in a tool description (empty = clean)."""
    findings: list[str] = []
    if len(description) > MAX_DESCRIPTION:
        findings.append(f"description is {len(description)} chars (>{MAX_DESCRIPTION})")
    for ch in description:
        cat = unicodedata.category(ch)
        if cat in ("Cf", "Cc") and ch not in "\n\t":
            findings.append(
                f"format/control char U+{ord(ch):04X} {unicodedata.name(ch, '?')} in description")
            break
    if "<!--" in description or "-->" in description:
        findings.append("HTML comment embedded in description (hidden instruction channel)")
    m = OVERRIDE_PHRASES.search(description)
    if m:
        findings.append(f"instruction-override phrase: {m.group(0)!r}")
    return findings


def pin_path(server: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", server)
    return PIN_DIR / f"{safe}.json"


def tool_fingerprint(name: str, description: str, signature: str) -> str:
    blob = json.dumps(
        {"name": name, "description": description, "signature": signature},
        sort_keys=True,
    ).encode()
    return hashlib.sha256(blob).hexdigest()


def load_pins(server: str) -> dict[str, str]:
    path = pin_path(server)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ToolPinDrift(
            f"pin file {path} unreadable ({e}); refusing to guess — inspect it"
        ) from e
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ToolPinDrift(f"pin file {path} malformed; refusing to guess — inspect it")
    return data


def learn_pins(server: str, pins: dict[str, str]) -> None:
    PIN_DIR.mkdir(parents=True, exist_ok=True)
    pin_path(server).write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n")


def verify_tool(server: str, name: str, description: str, fn: object | None = None) -> None:
    """Enforce the pin for one tool registration. Raises on drift/poisoning."""
    markers = scan_description(description)
    if markers:
        raise ToolPoisoningMarker(
            f"{server}/{name}: description failed the poisoning scan: {'; '.join(markers)}"
        )

    signature = ""
    if fn is not None:
        try:
            signature = str(inspect.signature(fn))
        except (TypeError, ValueError):
            signature = ""

    fp = tool_fingerprint(name, description, signature)
    pins = load_pins(server)

    if not pins:
        pins = {name: fp}
        learn_pins(server, pins)
        print(
            f"[tool-pins] {server}: learned first pin for {name} "
            f"(trust-on-first-use; re-pin via python -m shesh_audit.tool_pins --repin {server})",
            file=sys.stderr,
        )
        return

    existing = pins.get(name)
    if existing is None:
        raise ToolPinDrift(
            f"{server}/{name}: tool was not present in the pin set. "
            f"Explicit re-pin required: python -m shesh_audit.tool_pins --repin {server}"
        )

    if existing != fp:
        raise ToolPinDrift(
            f"{server}/{name}: tool definition changed since it was pinned (rug-pull defense). "
            f"If this change is intended: python -m shesh_audit.tool_pins --repin {server}"
        )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) == 2 and argv[0] == "--repin":
        path = pin_path(argv[1])
        if path.exists():
            path.unlink()
        print(
            f"[tool-pins] {argv[1]}: pins cleared; next server boot relearns them",
            file=sys.stderr,
        )
        return 0
    print(__doc__.splitlines()[0], file=sys.stderr)
    print("usage: python -m shesh_audit.tool_pins --repin <server-name>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
