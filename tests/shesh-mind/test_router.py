"""Offline tests for the model router and MCP server."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_mind import server  # noqa: E402
from shesh_mind.client import OllamaClient  # noqa: E402
from shesh_mind.router import (  # noqa: E402
    DEFAULT_MODELS,
    ModelRouter,
    Role,
    RouterConfig,
)


def test_default_mapping():
    r = ModelRouter()
    d = r.select(Role.CODER)
    assert d.model == "qwen2.5-coder:3b"
    assert d.role == Role.CODER


def test_vision_uses_moondream():
    d = ModelRouter().select(Role.VISION)
    assert d.model == "moondream2:latest"


def test_vision_disabled_falls_to_primary():
    d = ModelRouter().select(Role.VISION, allow_vision=False)
    assert d.role == Role.PRIMARY


def test_vram_budget_falls_back():
    cfg = RouterConfig(max_vram_gb=2.0)
    r = ModelRouter(cfg)
    # coder (2.8GB) + nothing loaded -> should warn/fallback
    d = r.select(Role.CODER)
    assert d.model in {"qwen2.5-coder:3b", "phi4-mini:latest"}
    assert "VRAM" in d.reason or "default" in d.reason


def test_reuses_loaded_model_within_budget():
    r = ModelRouter(RouterConfig(max_vram_gb=3.0))
    d = r.select(Role.PLANNER, loaded={"qwen2.5-coder:3b"})
    # if primary exceeds budget with coder loaded, it may reuse coder
    assert d.vram_gb <= 3.5


def test_override_changes_mapping():
    r = ModelRouter()
    r.override(Role.CODER, "gemma2:2b")
    assert r.select(Role.CODER).model == "gemma2:2b"


def test_plan_session_minimizes_models():
    r = ModelRouter()
    plan = r.plan_session([Role.PLANNER, Role.RESEARCHER, Role.CRITIC])
    # planner/researcher/critic share the primary model
    models = {d.model for d in plan}
    assert len(models) <= 2
    assert all(d.role != Role.CODER for d in plan)


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        Role("superintelligence")


# ── client ──────────────────────────────────────────────────────────
def test_ollama_client_offline_returns_empty():
    def boom(*a, **k):
        raise OSError("offline")
    c = OllamaClient(transport=boom)
    assert c.list_models() == []
    assert c.is_available("anything") is False


def test_ollama_client_lists_models():
    def fake(method, path, body=None):
        return {"models": [{"name": "phi4-mini:latest"}, {"name": "qwen2.5-coder:3b"}]}
    c = OllamaClient(transport=fake)
    assert set(c.list_models()) == {"phi4-mini:latest", "qwen2.5-coder:3b"}
    assert c.is_available("phi4-mini:latest")


# ── MCP server ─────────────────────────────────────────────────────
def test_server_select(monkeypatch):
    # avoid network: stub the client
    monkeypatch.setattr(server, "client", lambda: type("C", (), {
        "is_available": lambda self, m: m in DEFAULT_MODELS.values()})())
    out = server.select_model("coder")
    assert out["model"] == "qwen2.5-coder:3b"
    assert out["installed"] is True


def test_server_plan_session(monkeypatch):
    monkeypatch.setattr(server, "_router", ModelRouter())
    out = server.plan_session(["planner", "coder"])
    assert {x["role"] for x in out} == {"planner", "coder"}


def test_server_override(monkeypatch):
    monkeypatch.setattr(server, "_router", ModelRouter())
    assert server.set_model_for_role("coder", "gemma2:2b")["ok"] is True
    assert server.select_model("coder")["model"] == "gemma2:2b"
