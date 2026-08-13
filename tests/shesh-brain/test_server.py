from shesh_brain.server import get_policy, route_tool_call


def test_route():
    res = route_tool_call("test", "get_system_status", {})
    assert "allowed" in res

def test_policy():
    res = get_policy()
    assert isinstance(res, dict)
