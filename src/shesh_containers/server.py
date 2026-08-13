"""MCP server for podman/distrobox sandboxed execution."""
from __future__ import annotations

from shesh_audit.mcp_guard import GuardedMCP as _MCP

from .runner import (
    ContainerConfig,
    container_available,
    run_in_container,
)
from .runner import (
    list_images as _list_images,
)
from .runner import (
    pull as _pull,
)

mcp = _MCP("shesh-containers")
_cfg = ContainerConfig()


@mcp.tool()
def run_sandboxed(command: list[str], image: str | None = None,
                  timeout: int = 60, network: str = "none") -> dict:
    """Run a command in an unprivileged, network-isolated container.

    Returns the exit code and output. The container is removed after.
    """
    if not container_available(_cfg.engine):
        return {"ok": False, "error": f"{_cfg.engine} not installed"}
    cfg = ContainerConfig(
        engine=_cfg.engine, image=image or _cfg.image,
        timeout=timeout, network=network)
    return run_in_container(command, cfg)


@mcp.tool()
def list_container_images() -> dict:
    """List locally available container images."""
    if not container_available(_cfg.engine):
        return {"ok": False, "error": f"{_cfg.engine} not installed"}
    return {"ok": True, "images": _list_images(_cfg)}


@mcp.tool()
def pull_image(image: str) -> dict:
    """Pull a container image."""
    return _pull(image, _cfg)


@mcp.tool()
def set_engine(engine: str) -> dict:
    """Switch the container engine (podman|docker|distrobox)."""
    if engine not in {"podman", "docker", "distrobox"}:
        return {"ok": False, "error": "unsupported engine"}
    _cfg.engine = engine
    return {"ok": True, "engine": engine}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
