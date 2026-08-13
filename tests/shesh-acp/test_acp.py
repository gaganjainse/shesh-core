"""Offline tests for the ACP server (no stdio, no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shesh_acp import protocol as p  # noqa: E402
from shesh_acp.server import ACPServer  # noqa: E402


def make_server(tmp_path, **kw):
    return ACPServer(root=tmp_path, **kw)


def test_initialize_returns_capabilities():
    srv = make_server(Path("/tmp"))
    out = srv.handle(p.request(1, "initialize", {}))
    assert out[0]["result"]["name"] == "shesh-acp"
    assert "fs" in out[0]["result"]["capabilities"]


def test_unknown_method_returns_error():
    srv = make_server(Path("/tmp"))
    out = srv.handle(p.request(1, "nope"))
    assert "error" in out[0]


def test_session_and_file_roundtrip(tmp_path):
    srv = make_server(tmp_path, policy=lambda kind: "allow")
    sid = srv.handle(p.request(1, "session/new", {"cwd": str(tmp_path)}))[0]["result"]["sessionId"]

    # write
    w = srv.handle(p.request(2, "fs/write_text_file", {
        "sessionId": sid, "path": "a/b.txt", "text": "hello"}))
    assert w[0]["result"]["ok"] is True
    assert (tmp_path / "a/b.txt").read_text() == "hello"

    # read
    r = srv.handle(p.request(3, "fs/read_text_file", {
        "sessionId": sid, "path": "a/b.txt"}))
    assert r[0]["result"]["text"] == "hello"

    # list
    lst = srv.handle(p.request(4, "fs/list", {"sessionId": sid}))
    names = [e["name"] for e in lst[0]["result"]["entries"]]
    assert "a" in names


def test_write_denied_by_policy(tmp_path):
    srv = make_server(tmp_path, policy=lambda kind: "deny")
    sid = srv.handle(p.request(1, "session/new", {"cwd": str(tmp_path)}))[0]["result"]["sessionId"]
    w = srv.handle(p.request(2, "fs/write_text_file", {
        "sessionId": sid, "path": "x.txt", "text": "x"}))
    assert w[0]["result"]["ok"] is False
    assert not (tmp_path / "x.txt").exists()


def test_path_traversal_blocked(tmp_path):
    srv = make_server(tmp_path, policy=lambda kind: "allow")
    sid = srv.handle(p.request(1, "session/new", {"cwd": str(tmp_path)}))[0]["result"]["sessionId"]
    out = srv.handle(p.request(2, "fs/read_text_file", {
        "sessionId": sid, "path": "../../etc/passwd"}))
    assert "error" in out[0]


def test_prompt_streams_updates(tmp_path):
    def fake_agent(prompt, ctx):
        yield {"type": "delta", "delta": "ok:" + prompt}
        yield {"type": "done", "sessionId": ctx["session"]}

    srv = make_server(tmp_path, agent_run=fake_agent)
    sid = srv.handle(p.request(1, "session/new", {"cwd": str(tmp_path)}))[0]["result"]["sessionId"]
    out = srv.handle(p.request(2, "session/prompt", {"sessionId": sid, "prompt": "hi"}))
    # prompt has no id -> notifications only; at least one session/update + done
    assert any(m["method"] == "session/update" for m in out)
    assert any(m.get("params", {}).get("type") == "done" for m in out)


def test_notifications_have_no_id():
    n = p.notification("x", {"a": 1})
    assert "id" not in n
    assert n["method"] == "x"


def test_session_cancel(tmp_path):
    s = make_server(tmp_path)
    r = s.handle(p.request(1, "session/new", {"cwd": str(tmp_path)}))
    sid = r[0]["result"]["sessionId"]
    out = s.handle(p.request(2, "session/cancel", {"sessionId": sid}))
    assert out[0]["result"]["ok"] is True
    assert s.sessions[sid].cancelled


def test_permission_response(tmp_path):
    s = make_server(tmp_path)
    out = s.handle(p.request(1, "session/permission_response",
        {"sessionId": "x", "requestId": "req1", "approved": True}))
    assert out[0]["result"]["approved"] is True
    assert s.pending_permissions["req1"] is True


def test_terminal_exec(tmp_path):
    from shesh_acp.server import ACPServer
    s = ACPServer(root=tmp_path)
    sid = s.handle(
        {"id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
    )[0]["result"]["sessionId"]
    out = s.handle({"id":2,"method":"terminal/exec",
                    "params":{"sessionId":sid,"command":"echo hello"}})
    assert out[0]["result"]["ok"] is True
    assert "hello" in out[0]["result"]["stdout"]


def test_terminal_requires_confirmation_for_dangerous(tmp_path):
    from shesh_acp.server import ACPServer
    s = ACPServer(root=tmp_path)
    sid = s.handle(
        {"id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
    )[0]["result"]["sessionId"]
    out = s.handle({"id":2,"method":"terminal/exec",
                    "params":{"sessionId":sid,"command":"rm -rf /"}})
    assert out[0]["result"].get("needs_confirmation") is True


def test_fs_diff(tmp_path):
    from shesh_acp.server import ACPServer
    s = ACPServer(root=tmp_path)
    (tmp_path / "f.txt").write_text("old\n")
    sid = s.handle(
        {"id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
    )[0]["result"]["sessionId"]
    r = s.handle({"id":2,"method":"fs/diff",
                  "params":{"sessionId":sid,"path":"f.txt","text":"new\n"}})
    assert "---" in "\n".join(r[0]["result"]["diff"]) or len(r[0]["result"]["diff"]) > 0
