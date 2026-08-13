"""Container command runner (podman/distrobox), injectable for tests."""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

Runner = Callable[[list[str], int], tuple[int, str]]


def default_runner(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


@dataclass
class ContainerConfig:
    engine: str = "podman"   # podman | docker | distrobox
    image: str = "docker.io/library/alpine:latest"
    name: str | None = None
    timeout: int = 60
    network: str = "none"    # none | host | bridge
    pids_limit: int = 64


def container_available(engine: str = "podman") -> bool:
    return shutil.which(engine) is not None


def run_in_container(command: list[str], cfg: ContainerConfig,
                     runner: Runner = default_runner) -> dict:
    """Run a command inside a fresh, unprivileged, network-isolated container."""
    args = [cfg.engine, "run", "--rm", "-i",
            f"--network={cfg.network}", f"--pids-limit={cfg.pids_limit}",
            "--cap-drop=ALL"]
    if cfg.name:
        args += ["--name", cfg.name]
    args += [cfg.image] + command
    rc, out = runner(args, cfg.timeout)
    return {"ok": rc == 0, "exit_code": rc, "output": out[-4000:]}


def list_images(cfg: ContainerConfig, runner: Runner = default_runner) -> list[str]:
    rc, out = runner([cfg.engine, "images", "--format", "{{.Repository}}:{{.Tag}}"], 30)
    return out.splitlines() if rc == 0 else []


def pull(image: str, cfg: ContainerConfig, runner: Runner = default_runner) -> dict:
    rc, out = runner([cfg.engine, "pull", image], 300)
    return {"ok": rc == 0, "output": out[-2000:]}
