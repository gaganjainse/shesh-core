"""shesh-skills: everyday MCP tools and Markdown skills for the Shesh agent.

Tools are local-first and delegate to standard CLI utilities (gh, git, curl,
pandoc) so there is no large dependency surface. Everything is wrapped so tests
can monkeypatch the process runner without touching the real system.
"""
from __future__ import annotations

__version__ = "0.1.0"
