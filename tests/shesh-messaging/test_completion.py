"""Completion tests: read path (getUpdates) + connectivity probe (getMe) —
the send-only bridge becomes a full duplex one. Same disciplines as the
send path: opt-in flag, secret-resolved token, error taxonomy."""
import shesh_messaging.server as srv


def _enable(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    srv.enable_bridge("telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN")


def test_read_telegram_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    res = srv.read_telegram()
    assert res["ok"] is False and "not enabled" in res["error"]


def test_read_telegram_normalizes_updates(tmp_path, monkeypatch):
    _enable(monkeypatch, tmp_path)
    calls = {}

    def fake_api(token, method, payload, timeout=10):
        calls["method"] = method
        calls["payload"] = payload
        assert method == "getUpdates"
        return {"ok": True, "result": [
            {"update_id": 100, "message": {"chat": {"id": 7},
             "from": {"username": "gagan"}, "text": "hi", "date": 1}},
            {"update_id": 101, "channel_post": {"chat": {"id": 8},
             "text": "announce", "date": 2}},
        ]}

    monkeypatch.setattr(srv, "_telegram_api", fake_api)
    res = srv.read_telegram(offset=50, limit=5, timeout=3)
    assert res["ok"] is True and res["count"] == 2
    assert res["messages"][0] == {"update_id": 100, "chat_id": 7,
                                  "from": "gagan", "text": "hi", "date": 1}
    assert res["messages"][1]["chat_id"] == 8  # channel_post handled too
    assert res["next_offset"] == 102  # max(update_id)+1 acknowledges
    assert calls["payload"] == {"offset": 50, "limit": 5, "timeout": 3}
    srv.disable_bridge("telegram")


def test_read_telegram_empty_keeps_offset(tmp_path, monkeypatch):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(srv, "_telegram_api",
                        lambda *a, **k: {"ok": True, "result": []})
    res = srv.read_telegram(offset=77)
    assert res["count"] == 0 and res["next_offset"] == 77
    srv.disable_bridge("telegram")


def test_read_telegram_api_error(tmp_path, monkeypatch):
    _enable(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise srv.TelegramAPIError(401, "unauthorized")

    monkeypatch.setattr(srv, "_telegram_api", boom)
    res = srv.read_telegram()
    assert res["ok"] is False and "telegram HTTP 401" in res["error"]
    srv.disable_bridge("telegram")


def test_telegram_status(tmp_path, monkeypatch):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(srv, "_telegram_api",
                        lambda *a, **k: {"ok": True, "result": {
                            "id": 1, "username": "sheshbot",
                            "can_read_all_group_messages": False}})
    res = srv.telegram_status()
    assert res["ok"] is True and res["username"] == "sheshbot"
    assert res["can_read"] is False
    srv.disable_bridge("telegram")


def test_telegram_status_no_token(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    srv.enable_bridge("telegram")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    res = srv.telegram_status()
    assert res["ok"] is False and "not found" in res["error"]
    srv.disable_bridge("telegram")
