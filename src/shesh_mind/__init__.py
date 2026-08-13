"""shesh-mind: model routing for the 6 GB-safe local stack.

Given a task role and context, pick which Ollama model should handle it.
The router is deterministic and config-driven so it's testable without a
running model and so a user can override every mapping.
"""
from __future__ import annotations

__version__ = "0.1.0"
