"""Tiny Ollama HTTP client used by the mind to list/generate.

Network access is isolated here so tests can inject a fake transport.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Transport = Callable[[str, str, dict | None], dict]


def http_transport(base_url: str = "http://localhost:11434") -> Transport:
    def _request(method: str, path: str, body: dict | None = None) -> dict:
        url = base_url.rstrip("/") + path
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    return _request


@dataclass
class OllamaClient:
    transport: Transport
    base_url: str = "http://localhost:11434"

    @classmethod
    def connect(cls, base_url: str = "http://localhost:11434") -> OllamaClient:
        return cls(transport=http_transport(base_url), base_url=base_url)

    def list_models(self) -> list[str]:
        try:
            data = self.transport("GET", "/api/tags", None)
        except (OSError, ValueError) as e:
            # Ollama unreachable or malformed reply: "no models" is the
            # designed offline answer, and it is announced, not silent.
            print(f"ollama list_models probe failed ({e}); reporting no models",
                  file=sys.stderr)
            return []
        return [m.get("name", "") for m in data.get("models", [])]

    def is_available(self, model: str) -> bool:
        return model in self.list_models()

    def generate(self, model: str, prompt: str, **opts: Any) -> str:
        body = {"model": model, "prompt": prompt, "stream": False, **opts}
        data = self.transport("POST", "/api/generate", body)
        return data.get("response", "")
