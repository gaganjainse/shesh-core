"""shesh-containers: MCP tools for podman/distrobox sandboxed execution.

Agents can run commands inside a disposable container rather than on the
host. Every command is policy-checked (shesh-audit Guard) and the runner
enforces timeouts and no-privileged containers.
"""
from __future__ import annotations

__version__ = "0.1.0"
