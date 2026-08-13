"""shesh-audit: append-only, hash-chained event log + policy gate.

This is the Brain's conscience. Every action Shesh takes is recorded as an
event in an append-only JSONL log, each chained to the previous by SHA-256 so
tampering is detectable. A policy engine decides whether a proposed tool call
is allowed, requires confirmation, or is forbidden, and the decision itself is
logged.

It is intentionally simple/local (no database, no service dependency) so it can
be the foundation that SheshAOS-style governance plugs into later.
"""
from __future__ import annotations

__version__ = "0.1.0"
