"""Policy decisions for tool calls.

Three verdicts: allow, confirm, deny. Rules are evaluated in order; the first
matching rule wins. Defaults to "confirm" for unknown actions so Shesh never
silently does something surprising.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import StrEnum


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
                target = str(args.get("path") or args.get("file") or "")
                if not fnmatch.fnmatch(target, r.path_glob):
                    continue
            return r.verdict, r.reason
        return Verdict.CONFIRM, "unknown action; default confirm"


def default_policy() -> Policy:
    """The default safe policy for a personal laptop."""
    return Policy(rules=[
        # Read-only / informational: allow silently
        Rule(Verdict.ALLOW, "get_*", reason="read-only"),
        Rule(Verdict.ALLOW, "list_*", reason="read-only"),
        Rule(Verdict.ALLOW, "search*", reason="read-only"),
        Rule(Verdict.ALLOW, "recall", reason="read-only"),
        Rule(Verdict.ALLOW, "assemble_context", reason="read-only"),
        # Protected paths: never touch, even to read
        Rule(Verdict.DENY, "*", path_glob="*/Documents/Job/*", reason="job data off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/Projects/job/*", reason="job data off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/.ssh/*", reason="secrets off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/.gnupg/*", reason="secrets off-limits"),
        Rule(Verdict.DENY, "*", path_glob="*/Vaults/*", reason="vault off-limits"),
        # Destructive: always confirm
        Rule(Verdict.CONFIRM, "run_backup", reason="system change"),
        Rule(Verdict.CONFIRM, "set_power_profile", reason="system change"),
        Rule(Verdict.CONFIRM, "*", reason="default: ask before acting"),
    ])
