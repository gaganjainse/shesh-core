"""Completion tests: confirmation two-phase flow + audit read view + policy
content. These pin the routing contract, not just dict shapes."""
from shesh_brain.server import audit_tail, get_policy, record_confirmation, route_tool_call


def test_policy_exposes_rules_with_verdicts():
    res = get_policy()
    assert res["guard"] is True
    assert res["rule_count"] == len(res["rules"])
    assert res["rule_count"] > 0
    for rule in res["rules"]:
        assert set(rule) == {"tool", "verdict", "reason"}
        assert rule["verdict"] in ("allow", "confirm", "deny")


def test_route_tool_call_records_every_decision():
    route_tool_call("audited-actor-xyz", "get_system_status", {})
    route_tool_call("audited-actor-xyz", "nonexistent_tool_abc", {})
    events = audit_tail(10)["events"]
    ours = [e for e in events if e.get("actor") == "audited-actor-xyz"]
    assert len(ours) == 2, "every routing decision must land in the audit log"
    assert {e.get("action") for e in ours} == {"get_system_status", "nonexistent_tool_abc"}


def test_route_tool_call_none_args_accepted():
    res = route_tool_call("tester", "get_system_status", None)
    assert "allowed" in res and "verdict" in res


def test_confirmation_grant_flow():
    res = record_confirmation("tester", "some_tool", approved=True, reason="human said yes")
    assert res["ok"] is True
    assert res["may_execute"] is True
    assert res["verdict"] == "confirmation-granted"


def test_confirmation_deny_flow_lands_in_audit():
    res = record_confirmation("tester", "some_tool", approved=False, reason="human refused")
    assert res["may_execute"] is False
    events = audit_tail(10)["events"]
    assert any(e.get("verdict") == "confirmation-denied" for e in events), \
        "a denied confirmation must be visible in the audit tail"


def test_audit_tail_limit_clamped():
    assert audit_tail(0)["ok"]  # clamps to >=1 rather than erroring
    res = audit_tail(3)
    assert res["count"] <= 3
    assert res["count"] == len(res["events"])
