"""Policy decisions for tool calls.

Three verdicts: allow, confirm, deny. Rules are evaluated in order; the first
matching rule wins. Defaults to "confirm" for unknown actions so Shesh never
silently does something surprising.

The policy is configurable without touching code: ``~/.config/shesh/policy.json``
(or ``SHESH_POLICY``) may set the default verdict for unmatched actions and
whether protected paths (job data, secrets, vaults) are hard-denied. The desktop
Settings → Shesh → Governance page writes this file.
"""
from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Verdict(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class Rule:
    verdict: Verdict
    tool: str = "*"          # glob match on tool name
    path_glob: str | None = None
    reason: str = ""


@dataclass
class Policy:
    rules: list[Rule] = field(default_factory=list)

    def decide(self, tool: str, args: dict | None = None) -> tuple[Verdict, str]:
        args = args or {}
        for r in self.rules:
            if not fnmatch.fnmatch(tool, r.tool):
                continue
            if r.path_glob is not None:
                # Collect candidate paths from multiple possible arg keys
                raw_paths: list[str] = []
                for key in ("path", "file", "file_path", "source", "target", "dir", "directory"):
                    if key in args:
                        raw_paths.append(str(args[key]))
                # Canonicalize each path gracefully (os.path.realpath if the path exists)
                candidates: list[str] = []
                for p in raw_paths:
                    try:
                        candidates.append(os.path.realpath(p) if os.path.exists(p) else p)
                    except Exception:
                        candidates.append(p)
                # Check if any candidate matches the glob
                if not any(fnmatch.fnmatch(c, r.path_glob) for c in candidates):
                    continue
            return r.verdict, r.reason
        return Verdict.CONFIRM, "unknown action; default confirm"


def default_policy() -> Policy:
    """The default safe policy for a personal laptop."""
    return Policy(rules=[
        # Protected paths must precede broad read-only rules. Policy uses
        # first-match semantics, so placing these after get_* would allow
        # confidential reads despite the intended hard deny.
        Rule(Verdict.DENY, "*", path_glob="*/Documents/Job/*", reason="job data off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/Projects/job/*", reason="job data off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/.ssh/*", reason="secrets off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/.gnupg/*", reason="secrets off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/Vaults/*", reason="vault off-limits"),
        # Read-only / informational: allow silently
        Rule(Verdict.ALLOW, "get_*", reason="read-only"),
        Rule(Verdict.ALLOW, "list_*", reason="read-only"),
        Rule(Verdict.ALLOW, "search*", reason="read-only"),
        Rule(Verdict.ALLOW, "recall", reason="read-only"),
        Rule(Verdict.ALLOW, "assemble_context", reason="read-only"),
        # Destructive: always confirm
        Rule(Verdict.CONFIRM, "run_backup", reason="system change"),
        Rule(Verdict.CONFIRM, "set_power_profile", reason="system change"),
        Rule(Verdict.CONFIRM, "*", reason="default: ask before acting"),
    ])


POLICY_PATH = Path(os.environ.get(
    "SHESH_POLICY",
    os.path.expanduser("~/.config/shesh/policy.json"),
))

PROTECTED_GLOBS = [
    ("*/Documents/Job/*", "job data off-limits"),
    ("*/Projects/job/*", "job data off-limits"),
    ("*/.ssh/*", "secrets off-limits"),
    ("*/.gnupg/*", "secrets off-limits"),
    ("*/Vaults/*", "vault off-limits"),
]


def load_policy(path: Path | None = None) -> Policy:
    """Build the policy from ~/.config/shesh/policy.json (or SHESH_POLICY).

    Format::

        {"default_verdict": "confirm", "protected_paths": true}

    Missing/corrupt file → default_policy(). The file is written by the desktop
    Settings → Shesh → Governance page (or save_policy below).
    """
    p = Path(path) if path else POLICY_PATH
    data: dict | None = None
    if p.exists():
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            data = None
    if not isinstance(data, dict):
        return default_policy()

    verdict = data.get("default_verdict", "confirm")
    if verdict not in ("allow", "confirm", "deny"):
        verdict = "confirm"
    protected = bool(data.get("protected_paths", True))

    if protected:
        rules: list[Rule] = [
            *(Rule(Verdict.DENY, "*", path_glob=g, reason=r) for g, r in PROTECTED_GLOBS),
            Rule(Verdict.ALLOW, "get_*", reason="read-only"),
            Rule(Verdict.ALLOW, "list_*", reason="read-only"),
            Rule(Verdict.ALLOW, "search*", reason="read-only"),
            Rule(Verdict.ALLOW, "recall", reason="read-only"),
            Rule(Verdict.ALLOW, "assemble_context", reason="read-only"),
            Rule(Verdict.CONFIRM, "run_backup", reason="system change"),
            Rule(Verdict.CONFIRM, "set_power_profile", reason="system change"),
        ]
    else:
        rules: list[Rule] = [
            Rule(Verdict.ALLOW, "get_*", reason="read-only"),
            Rule(Verdict.ALLOW, "list_*", reason="read-only"),
            Rule(Verdict.ALLOW, "search*", reason="read-only"),
            Rule(Verdict.ALLOW, "recall", reason="read-only"),
            Rule(Verdict.ALLOW, "assemble_context", reason="read-only"),
            Rule(Verdict.CONFIRM, "run_backup", reason="system change"),
            Rule(Verdict.CONFIRM, "set_power_profile", reason="system change"),
        ]
    rules.append(Rule(Verdict(verdict), "*", reason=f"default from policy.json: {verdict}"))
    return Policy(rules=rules)


class PolicyConfigError(ValueError):
    """Invalid policy.json content (bad verdict, etc.)."""

    def __init__(self, verdict: str) -> None:
        super().__init__(f"invalid default_verdict {verdict!r}")


def save_policy(default_verdict: str, protected_paths: bool, path: Path | None = None) -> Path:
    """Write policy.json (used by the desktop settings page / installer)."""
    p = Path(path) if path else POLICY_PATH
    if default_verdict not in ("allow", "confirm", "deny"):
        raise PolicyConfigError(default_verdict)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": 1,
        "default_verdict": default_verdict,
        "protected_paths": bool(protected_paths),
    }, indent=2) + "\n")
    return p
