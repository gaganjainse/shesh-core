#!/usr/bin/env python3
"""stdio entry point: read JSON-RPC lines, dispatch, write responses."""
from __future__ import annotations

import json
import sys

from .server import ACPServer


def main() -> int:
    srv = ACPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }) + "\n")
            sys.stdout.flush()
            continue
        for out in srv.handle(msg):
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
