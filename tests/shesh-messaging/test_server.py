from shesh_messaging.server import disable_bridge, enable_bridge, list_bridges, send_telegram


def test_list():
    res = list_bridges()
    assert "telegram" in res

def test_send_disabled():
    res = send_telegram("123", "hello")
    assert res["ok"] is False  # not enabled by default

def test_enable_disable():
    enable_bridge("telegram")
    res = list_bridges()
    assert res["telegram"]["enabled"] is True
    disable_bridge("telegram")
    res = list_bridges()
    assert res["telegram"]["enabled"] is False


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json as _json

        return _json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_telegram_real_api(monkeypatch, tmp_path):
    """Enabled bridge + token + mocked Bot API -> real request made."""
    import shesh_messaging.server as srv

    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    srv.enable_bridge("telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN")

    calls = {}

    def fake_urlopen(req, timeout=0):
        calls["url"] = req.full_url
        calls["body"] = req.data.decode()
        return _FakeResp({"ok": True, "result": {"message_id": 42, "date": 1}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    res = srv.send_telegram("123", "hello")
    assert res["ok"] is True and res["message_id"] == 42
    assert "api.telegram.org/botTESTTOKEN/sendMessage" in calls["url"]
    assert '"text": "hello"' in calls["body"]
    srv.disable_bridge("telegram")


def test_send_telegram_api_error(monkeypatch, tmp_path):
    import shesh_messaging.server as srv

    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    srv.enable_bridge("telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN")

    def boom(req, timeout=0):
        raise TimeoutError

    monkeypatch.setattr("urllib.request.urlopen", boom)
    res = srv.send_telegram("123", "hello")
    assert res["ok"] is False and "telegram request failed" in res["error"]
    srv.disable_bridge("telegram")


def test_send_signal_missing_cli(monkeypatch, tmp_path):
    import shesh_messaging.server as srv

    monkeypatch.setattr(srv, "BRIDGE_DIR", tmp_path)
    srv.enable_bridge("signal")
    monkeypatch.setattr("shutil.which", lambda name: None)
    res = srv.send_signal("+1000", "hi")
    assert res["ok"] is False and "signal-cli not installed" in res["error"]
    srv.disable_bridge("signal")
