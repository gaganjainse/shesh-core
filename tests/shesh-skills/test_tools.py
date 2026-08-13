"""Offline tests for shesh-skills (no network, no real git/gh)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import shesh_skills.tools as t  # noqa: E402


def test_append_note_creates_and_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DEFAULT_VAULT", tmp_path)
    r1 = t.append_note("ideas", "buy milk", timestamp=False)
    r2 = t.append_note("ideas", "walk dog", timestamp=False)
    assert r1["ok"] and (tmp_path / "ideas.md").exists()
    text = (tmp_path / "ideas.md").read_text()
    assert "buy milk" in text and "walk dog" in text
    assert r2["path"].endswith("ideas.md")


def test_append_note_sanitizes_names(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DEFAULT_VAULT", tmp_path)
    r = t.append_note("../evil", "x", timestamp=False)
    # path traversal is sanitized to a safe filename under the vault
    assert Path(r["path"]).parent.resolve() == tmp_path.resolve()
    assert "/" not in Path(r["path"]).name


def test_find_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DEFAULT_VAULT", tmp_path)
    (tmp_path / "Rust.md").write_text("a")
    (tmp_path / "python.md").write_text("b")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "rust-notes.md").write_text("c")
    assert set(t.find_notes("rust")) == {"Rust.md", "sub/rust-notes.md"}


def test_search_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DEFAULT_VAULT", tmp_path)
    (tmp_path / "a.md").write_text("apple pie\nbanana\n")
    (tmp_path / "b.md").write_text("cherry\n")
    res = t.search_notes("apple")
    assert len(res) == 1
    assert res[0]["file"] == "a.md"
    assert any("apple pie" in m for m in res[0]["matches"])


def test_search_missing_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "DEFAULT_VAULT", tmp_path / "nope")
    assert t.search_notes("x") == []


def test_dgg_search_parses_results(monkeypatch):
    fake_html = '''
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F">Example</a>
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftwo.test%2F">Two</a>
    '''
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return fake_html.encode()
    monkeypatch.setattr(t.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    res = t.duckduckgo_search("test", 5)
    assert len(res) == 2
    assert res[0] == {"title": "Example", "url": "https://example.com/"}
    assert res[1]["url"] == "https://two.test/"


def test_fetch_url_strips_html(monkeypatch):
    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=0):
            return b"<html><script>bad()</script><b>Hi</b> there</html>"
    monkeypatch.setattr(t.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    r = t.fetch_url("https://x")
    assert "error" not in r
    assert "Hi" in r["text"] and "bad()" not in r["text"]


def test_git_status_delegates(monkeypatch):
    seen = []
    monkeypatch.setattr(
        t, "run",
        lambda cmd, **k: (seen.append(cmd), type("R", (), {"text": "M foo"})())[1],
    )
    assert t.git_status("/repo") == "M foo"
    assert seen[0] == ["git", "-C", "/repo", "status", "--short", "--branch"]


def test_remind_uses_at_when_available(monkeypatch):
    # Pretend `at` exists
    monkeypatch.setattr(t, "run", lambda cmd, **k: type("R", (), {"ok": True, "text": ""})())
    r = t.remind(5, "drink water")
    assert r["ok"] and r["in_minutes"] == 5


def test_convert_uses_pandoc(monkeypatch):
    monkeypatch.setattr(t, "run",
        lambda cmd, **k: type("R", (), {"ok": True, "stdout": "# hi", "stderr": ""})())
    assert "# hi" in t.convert_to_markdown("x.docx")
