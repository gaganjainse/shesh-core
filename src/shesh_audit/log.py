"""Append-only hash-chained event log."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "shesh" / "audit"
_LEGACY_DATA_DIR = Path.home() / ".local" / "share" / "shesh" / "audit"
if _LEGACY_DATA_DIR.exists() and not DATA_DIR.exists():
    _LEGACY_DATA_DIR.rename(DATA_DIR)  # one-shot migration; legacy name is gone


@dataclass
class Event:
    ts: float
    actor: str           # which agent/role
    action: str          # tool/method name
    verdict: str         # allow | confirm | deny | executed | failed
    args: dict = field(default_factory=dict)
    result: str = ""
    prev_hash: str = ""
    hash: str = ""

    def payload(self) -> dict:
        d = asdict(self)
        d.pop("hash", None)
        return d


def _hash(payload: dict, prev: str) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False) + prev
    return hashlib.sha256(blob.encode()).hexdigest()


class AuditLog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.jsonl"
        self._last_hash = self._tail_hash()

    def _tail_hash(self) -> str:
        if not self.path.exists():
            return ""
        last = ""
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = line
        if not last:
            return ""
        try:
            return json.loads(last).get("hash", "")
        except json.JSONDecodeError:
            return ""

    def record(
        self,
        actor: str,
        action: str,
        verdict: str,
        *,
        args: dict | None = None,
        result: str = "",
    ) -> Event:
        ev = Event(
            ts=time.time(), actor=actor, action=action, verdict=verdict,
            args=args or {}, result=result, prev_hash=self._last_hash,
        )
        ev.hash = _hash(ev.payload(), ev.prev_hash)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ev), ensure_ascii=False) + "\n")
        self._last_hash = ev.hash
        return ev

    def verify(self) -> tuple[bool, int]:
        """Return (ok, bad_line). Walks the chain checking hashes."""
        if not self.path.exists():
            return True, 0
        prev = ""
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            stored = obj.pop("hash", "")
            if obj.get("prev_hash") != prev or stored != _hash(obj, prev):
                return False, i
            prev = stored
        return True, 0

    def recent(self, n: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
