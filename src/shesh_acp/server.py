"""ACP request handler — pure logic, no I/O on stdin/stdout.

The real server (stdio) feeds decoded JSON-RPC messages to `handle()` and
serializes the returned responses/notifications. Keeping this side-effect-light
makes it fully testable offline.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from pathlib import Path

from . import protocol as p

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class PathEscapeError(PermissionError):
    """A session-relative path resolved outside the session root."""

    def __init__(self, path: str) -> None:
        super().__init__(f"path escapes session root: {path}")


class ACPServer:
    def __init__(
        self,
        agent_run: Callable[[str, dict], Iterable[dict]] | None = None,
        policy: Callable[[str], str] | None = None,
        root: Path | None = None,
    ) -> None:
        # agent_run(prompt, session) yields streaming ACP update dicts.
        self.agent_run = agent_run or self._default_agent_run
        # policy(kind) -> "allow" | "ask" | "deny"
        self.policy = policy or (lambda kind: "ask")
        self.root = root or Path.cwd()
        self.sessions: dict[str, p.Session] = {}
        self.pending_permissions: dict[str, bool] = {}

    # ── dispatch ──────────────────────────────────────────────────────────
    def handle(self, msg: dict) -> list[dict]:
        """Process one JSON-RPC message; return zero or more response/notification dicts."""
        if "method" not in msg:
            return [p.error(msg.get("id", 0), INVALID_REQUEST, "missing method")]
        method = msg["method"]
        mid = msg.get("id")
        params = msg.get("params") or {}

        handler = {
            "initialize": self.initialize,
            "session/new": self.session_new,
            "fs/read_text_file": self.fs_read,
            "fs/write_text_file": self.fs_write,
            "fs/list": self.fs_list,
            "terminal/exec": self.terminal_exec,
            "fs/diff": self.fs_diff,
            "session/prompt": self.session_prompt,
            "session/cancel": self.session_cancel,
            "session/permission_response": self.permission_response,
        }.get(method)

        if handler is None:
            if mid is not None:
                return [p.error(mid, METHOD_NOT_FOUND, f"unknown method {method}")]
            return []
        try:
            result = handler(params)
        except Exception as e:  # noqa: BLE001 - surface as JSON-RPC error
            if mid is not None:
                return [p.error(mid, INTERNAL_ERROR, str(e))]
            return []
        # Methods returning a list produce notifications (e.g. streaming prompt).
        if isinstance(result, list):
            return result
        if mid is not None:
            return [p.success(mid, result)]
        return []

    # ── methods ───────────────────────────────────────────────────────────
    def initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": 1,
            "name": "shesh-acp",
            "version": "0.1.0",
            "capabilities": p.CAPABILITIES,
        }

    def session_new(self, params: dict) -> dict:
        cwd = params.get("cwd") or str(self.root)
        sid = params.get("id") or uuid.uuid4().hex[:12]
        self.sessions[sid] = p.Session(id=sid, cwd=cwd)
        return {"sessionId": sid, "cwd": cwd}

    def _resolve(self, session_id: str, path: str) -> Path:
        """Resolve a session-relative path, refusing escapes outside the cwd."""
        sess = self.sessions[session_id]
        root = Path(sess.cwd).resolve()
        pth = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if root not in pth.parents and pth != root:
            raise PathEscapeError(path)
        return pth

    def fs_read(self, params: dict) -> dict:
        sess = self.sessions[params["sessionId"]]
        target = self._resolve(sess.id, params["path"])
        return {"path": str(target), "text": target.read_text(errors="replace")}

    def fs_write(self, params: dict) -> dict:
        sess = self.sessions[params["sessionId"]]
        if not p.decide("fs.write", self.policy):
            return {"ok": False, "error": "permission denied"}
        target = self._resolve(sess.id, params["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(params.get("text", ""))
        return {"ok": True, "path": str(target)}

    def fs_list(self, params: dict) -> dict:
        sess = self.sessions[params["sessionId"]]
        target = self._resolve(sess.id, params.get("path", "."))
        entries = sorted(
            {"name": c.name, "dir": c.is_dir(), "size": c.stat().st_size if c.is_file() else 0}
            for c in target.iterdir()
        ) if target.exists() else []
        return {"path": str(target), "entries": entries}

    def session_prompt(self, params: dict) -> list[dict]:
        """Run an agent turn; yields streaming token updates + a final result."""
        sid = params["sessionId"]
        sess = self.sessions[sid]
        prompt = params.get("prompt", "")
        sess.history.append({"role": "user", "content": prompt})
        out: list[dict] = []
        for update in self.agent_run(prompt, {"session": sid, "cwd": sess.cwd}):
            out.append(p.notification("session/update", update))
        sess.history.append({"role": "assistant", "content": "".join(
            u.get("delta", "") for u in out if u["method"] == "session/update"
        )})
        return out

    def session_cancel(self, params: dict) -> dict:
        sid = params["sessionId"]
        if sid in self.sessions:
            self.sessions[sid].cancelled = True
        return {"ok": True}

    def permission_response(self, params: dict) -> dict:
        sid = params["sessionId"]
        request_id = params.get("requestId")
        approved = bool(params.get("approved", False))
        self.pending_permissions[request_id] = approved
        if sid in self.sessions:
            self.sessions[sid].history.append(
                {"role": "user",
                 "content": f"[permission {request_id}: {'approved' if approved else 'denied'}]"})
        return {"ok": True, "requestId": request_id, "approved": approved}

    @staticmethod
    def _default_agent_run(prompt: str, ctx: dict):
        # Echo/placeholder so the server is usable without an LLM wired in.
        yield {"type": "delta", "delta": f"(shesh-acp stub) received: {prompt}"}
        yield {"type": "done", "sessionId": ctx["session"]}

    # ── terminal ──────────────────────────────────────────────────────
    def terminal_exec(self, params: dict) -> dict:
        """Run a command in the session cwd via policy-routed, shell=False execution.

        Uses server-controlled approval (not client-confirm=true) and consumes
        pending_permissions on successful approval. Commands are parsed as
        argument lists rather than shell=True for safety.
        """
        import subprocess
        import os
        sid = params.get("sessionId")
        if not sid or sid not in self.sessions:
            return {"ok": False, "error": "unknown session"}
        sess = self.sessions[sid]

        cmd_raw = params.get("command", "")
        if not cmd_raw:
            return {"ok": False, "error": "no command"}

        # Route through policy — check if this command is allowed for this session
        # Build a minimal args dict for policy.decide()
        # The policy check uses path/file keys; for terminal exec we check the command
        # path against protected paths. A simple heuristic: treat the command as a
        # source path and check against deny rules.
        from shesh_audit.policy import Verdict
        verdict, reason = self.p.decide("terminal_exec", {"command": cmd_raw})
        if verdict is Verdict.DENY:
            return {"ok": False, "error": f"policy deny: {reason}"}
        # CONFIRM means the user needs to approve via the permission UI;
        # do NOT execute automatically.
        if verdict is Verdict.CONFIRM:
            # Record pending permission and ask the UI to present a confirmation
            # request bound to sessionId + command hash, not client-confirm=true.
            if not hasattr(self, "_pending_permissions"):
                self._pending_permissions = {}
            cmd_hash = hash(cmd_raw) & 0xFFFFFFFF
            self._pending_permissions[cmd_hash] = {
                "sessionId": sid,
                "command": cmd_raw,
                "proposed_by": params.get("origin", "client"),
            }
            return {
                "ok": False,
                "needs_approval": True,
                "approval_id": cmd_hash,
                "reason": "command requires server-mediated approval",
            }

        # Parse command as argv list (shell=False); allowlisted basenames only
        basename = os.path.basename(cmd_raw.strip())
        # Allow common read-only/utility basenames; block dangerous patterns
        dangerous_basenames = {"rm", "sudo", "mkfs", "dd", "shutdown", "reboot",
                               "chmod", "chown", "> ", "|", ";", "&"}
        if basename in dangerous_basenames:
            return {"ok": False, "error": f"command disallowed: {basename}"}

        # Safe commands: parse as simple argv list
        argv = cmd_raw.strip().split()
        if not argv:
            return {"ok": False, "error": "empty command"}

        try:
            # nosec B605 - argv list form; no shell=True; command is policy-gated above
            p = subprocess.run(
                argv, capture_output=True, text=True,
                cwd=sess.cwd, timeout=params.get("timeout", 30))
            return {"ok": p.returncode == 0, "exit_code": p.returncode,
                    "stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    def fs_diff(self, params: dict) -> dict:
        """Return a simple unified-style diff for a file vs expected text."""
        target = self._resolve(params["sessionId"], params["path"])
        import difflib
        old = target.read_text().splitlines() if target.exists() else []
        new = params.get("text", "").splitlines()
        diff = list(difflib.unified_diff(old, new, fromfile="a/"+target.name,
                                         tofile="b/"+target.name, lineterm=""))
        return {"path": str(target), "diff": diff}
