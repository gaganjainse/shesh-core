"""MCP server exposing secret resolution (no secret values are logged)."""
from __future__ import annotations

from . import is_secret_reference, resolve

try:
    from fastmcp import FastMCP
    mcp = FastMCP("shesh-secrets")
except ImportError:  # pragma: no cover — MCP wrapper is optional; resolve() still works
    mcp = None


if mcp:
    @mcp.tool()
    def get_secret(reference: str) -> dict:
        """Resolve a secret reference (env:/gopass:/keepassxc:/file:).

        Returns metadata only on success; the value is returned but never
        written to logs. Returns not-found if the backend is unavailable.
        """
        if not is_secret_reference(reference):
            return {"ok": False, "error": "not a secret reference"}
        value = resolve(reference)
        if value is None:
            return {"ok": False, "error": "not found or backend unavailable"}
        return {"ok": True, "value": value}

    @mcp.tool()
    def resolve_config(config: dict) -> dict:
        """Replace any '<scheme>:...' values in config with resolved secrets."""
        resolved = {}
        for k, v in config.items():
            resolved[k] = resolve(v) if is_secret_reference(v) else v
        return resolved

    def main() -> None:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
