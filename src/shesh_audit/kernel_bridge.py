"""Bridge from Python Soma tools to the SheshAOS (Rust) kernel event store.

SheshAOS defines events with an EventId (UUIDv7), a monotonic sequence, an
EventKind enum, a timestamp, and a JSON payload. This bridge appends events to
a shared JSONL file in that shape so the Rust kernel can ingest them without a
running service. It is append-only and hash-chained via the main AuditLog, so
tampering remains detectable.

EventKind strings here mirror the Rust enum variants in
SheshAOS crates/shesh-kernel/src/events.rs.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path


class KernelEventKind(StrEnum):
    # Must match the Rust EventKind variant names.
    TOOL_REQUESTED = "ToolRequested"
    TOOL_COMPLETED = "ToolCompleted"
    TOOL_FAILED = "ToolFailed"
    POLICY_CHECKED = "PolicyChecked"
    POLICY_DENIED = "PolicyDenied"
    CONFIRMATION_REQUESTED = "ConfirmationRequested"
    CONFIRMATION_GRANTED = "ConfirmationGranted"
    CONFIRMATION_DENIED = "ConfirmationDenied"
    MODEL_REQUESTED = "ModelRequested"
    MODEL_RESPONDED = "ModelResponded"
    MODEL_FAILED = "ModelFailed"


@dataclass
class KernelEvent:
    event_id: str            # UUIDv7-ish (uuid4 until a uuid7 lib is added)
    sequence: int
    kind: str
    timestamp: str          # RFC3339 UTC
    payload: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class KernelBridge:
    """Append kernel-compatible events to a shared JSONL file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (
            Path.home() / ".local" / "share" / "shesh" / "audit" / "kernel-events.jsonl"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = self._tail_sequence()

    def _tail_sequence(self) -> int:
        if not self.path.exists():
            return 0
        try:
            last = self.path.read_text(encoding="utf-8").splitlines()[-1]
        except IndexError:
            return 0
        try:
            return int(json.loads(last).get("sequence", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            return 0

    def emit(self, kind: KernelEventKind, payload: dict | None = None) -> KernelEvent:
        self._seq += 1
        ev = KernelEvent(
            event_id=str(uuid.uuid4()),
            sequence=self._seq,
            kind=kind.value,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            payload=payload or {},
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(ev.to_json() + "\n")
        return ev

    def read(self) -> list[KernelEvent]:
        out: list[KernelEvent] = []
        if not self.path.exists():
            return out
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                out.append(KernelEvent(**d))
            except (json.JSONDecodeError, TypeError):
                continue
        return out
