"""Offline tests for the container runner and MCP server."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_containers.runner import (  # noqa: E402
    ContainerConfig,
    list_images,
    pull,
    run_in_container,
)


def fake_runner_factory(outputs):
    calls = []

    def _run(cmd, timeout=60):
        calls.append(cmd)
        return outputs.get(" ".join(cmd[:2]), (0, ""))
    _run.calls = calls
    return _run


def test_run_builds_podman_args():
    runner = fake_runner_factory({"podman run": (0, "hello")})
    cfg = ContainerConfig(image="alpine")
    r = run_in_container(["echo", "hi"], cfg, runner=runner)
    assert r["ok"] is True
    joined = " ".join(runner.calls[0])
    assert "--rm" in joined and "--network=none" in joined
    assert "--cap-drop=ALL" in joined and "alpine" in joined
    assert joined.endswith("echo hi")


def test_run_reports_failure():
    runner = fake_runner_factory({"podman run": (1, "boom")})
    r = run_in_container(["false"], ContainerConfig(), runner=runner)
    assert r["ok"] is False and "boom" in r["output"]


def test_list_images_parses_lines(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda e: "/usr/bin/podman")
    runner = fake_runner_factory(
        {"podman images": (0, "alpine:latest\nubuntu:24.04")})
    images = list_images(ContainerConfig(), runner=runner)
    assert images == ["alpine:latest", "ubuntu:24.04"]


def test_pull():
    runner = fake_runner_factory({"podman pull": (0, "done")})
    r = pull("alpine", ContainerConfig(), runner=runner)
    assert r["ok"] is True


def test_mcp_tools_exist():
    import shesh_containers.server as srv  # noqa: F401
    for name in ("run_sandboxed", "list_container_images", "pull_image", "set_engine"):
        assert hasattr(srv, name)
