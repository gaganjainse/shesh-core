"""MCP server exposing model routing to the orchestrator and skills."""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .client import OllamaClient, http_transport
from .router import ModelRouter, Role

mcp = _MCP("shesh-mind")

_router = ModelRouter()
_client: OllamaClient | None = None


def client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient(http_transport())
    return _client


@mcp.tool()
def select_model(role: str, allow_vision: bool = True,
                 loaded_models: list[str] | None = None) -> dict:
    """Return which model should handle a given role (planner/coder/vision...)."""
    try:
        r = Role(role)
    except ValueError:
        return {"error": f"unknown role {role!r}; valid: {[x.value for x in Role]}"}
    d = _router.select(r, loaded=set(loaded_models or []), allow_vision=allow_vision)
    return {
        "role": d.role.value, "model": d.model, "reason": d.reason,
        "vram_gb": d.vram_gb,
        "installed": client().is_available(d.model),
    }


@mcp.tool()
def plan_session(roles: list[str]) -> list[dict]:
    """Plan model assignments for a multi-role session, minimizing loaded models."""
    parsed: list[Role] = []
    for r in roles:
        try:
            parsed.append(Role(r))
        except ValueError:
            continue
    return [
        {"role": d.role.value, "model": d.model, "reason": d.reason, "vram_gb": d.vram_gb}
        for d in _router.plan_session(parsed)
    ]


@mcp.tool()
def list_roles() -> list[dict]:
    """List available roles and their default model."""
    return [{"role": r.value, "model": m} for r, m in _router.config.models.items()]


@mcp.tool()
def set_model_for_role(role: str, model: str) -> dict:
    """Override the model used for a role."""
    try:
        r = Role(role)
    except ValueError:
        return {"ok": False, "error": "unknown role"}
    _router.override(r, model)
    return {"ok": True, "role": r.value, "model": model}


@mcp.tool()
def list_installed_models() -> list[str]:
    """List models currently pulled in Ollama."""
    return client().list_models()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
