"""Tests for scripts/install-shesh-wave.sh.

Runs the real installer against a throwaway WAVETERM_CONFIG_DIR and asserts:
- theme install + idempotency
- backup is taken before replacing a diverged theme
- settings merge is non-destructive (keeps user keys, sets ai:* keys)
- widgets merge is non-destructive and idempotent
- --dry-run writes nothing
- OMNIROUTE env var is honoured for the AI base URL
- invalid JSON in an existing file is backed up, never crashes
"""
import json
import os
import pathlib
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]  # core root (tests/<mod>/ layout)
SCRIPT = REPO / "wave" / "scripts" / "install-shesh-wave.sh"


def run_install(wave_dir, *flags, env_extra=None):
    env = dict(os.environ)
    env["WAVETERM_CONFIG_DIR"] = str(wave_dir)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(SCRIPT), *flags],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )


@pytest.fixture()
def wave(tmp_path):
    d = tmp_path / "waveterm"
    d.mkdir()
    return d


def test_theme_installed_and_idempotent(wave):
    r1 = run_install(wave)
    assert r1.returncode == 0, r1.stderr
    theme = wave / "config" / "termthemes" / "shesh-dark.json"
    assert theme.exists()
    data = json.loads(theme.read_text())
    assert data["display:name"] == "Shesh Dark"
    before = theme.stat().st_mtime_ns
    r2 = run_install(wave)
    assert r2.returncode == 0, r2.stderr
    assert theme.stat().st_mtime_ns == before  # not rewritten
    assert "already installed" in r2.stdout
    # no backup created when nothing diverges
    assert not (wave / "backups").exists()


def test_diverged_theme_is_backed_up(wave):
    assert run_install(wave).returncode == 0
    theme = wave / "config" / "termthemes" / "shesh-dark.json"
    theme.write_text('{"display:name": "user custom"}\n')
    r = run_install(wave)
    assert r.returncode == 0, r.stderr
    backs = list(wave.glob("backups/shesh-*/shesh-dark.json.bak"))
    assert len(backs) == 1
    assert "user custom" in backs[0].read_text()
    assert json.loads(theme.read_text())["display:name"] == "Shesh Dark"


def test_settings_merge_preserves_user_keys(wave):
    cfg = wave / "config"
    cfg.mkdir()
    (cfg / "settings.json").write_text(json.dumps({
        "term:fontsize": 15,
        "ai:baseurl": "https://old.example.com/v1",
    }))
    r = run_install(wave, "--with-local-ai")
    assert r.returncode == 0, r.stderr
    data = json.loads((cfg / "settings.json").read_text())
    assert data["term:fontsize"] == 15              # user key preserved
    assert data["ai:baseurl"] == "http://localhost:11434/v1"  # updated
    assert data["ai:apitoken"] == ""                # no key material, by policy


def test_settings_honour_omniroute(wave):
    r = run_install(
        wave, "--with-local-ai",
        env_extra={"SHESH_OMNIROUTE_BASE_URL": "http://localhost:20128/v1"},
    )
    assert r.returncode == 0, r.stderr
    data = json.loads((wave / "config" / "settings.json").read_text())
    assert data["ai:baseurl"] == "http://localhost:20128/v1"


def test_widgets_merge_idempotent_and_preserving(wave):
    cfg = wave / "config"
    cfg.mkdir()
    (cfg / "widgets.json").write_text(json.dumps({
        "user-widget": {"display:name": "Mine", "icon": "star"},
    }))
    r1 = run_install(wave, "--with-widgets")
    assert r1.returncode == 0, r1.stderr
    widgets = json.loads((cfg / "widgets.json").read_text())
    assert "user-widget" in widgets
    for key in ("shesh-sysmon", "shesh-files", "shesh-tasks"):
        assert key in widgets
    mtime = (cfg / "widgets.json").stat().st_mtime_ns
    r2 = run_install(wave, "--with-widgets")
    assert r2.returncode == 0, r2.stderr
    assert (cfg / "widgets.json").stat().st_mtime_ns == mtime


def test_dry_run_writes_nothing(wave):
    r = run_install(wave, "--with-local-ai", "--with-widgets", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "[dry-run]" in r.stdout
    assert not (wave / "config").exists()


def test_broken_existing_json_backed_up_not_crashing(wave):
    cfg = wave / "config"
    cfg.mkdir()
    (cfg / "settings.json").write_text("{not json!")
    r = run_install(wave, "--with-local-ai")
    assert r.returncode == 0, r.stderr
    assert (cfg / "settings.json.bak-before-shesh").read_text() == "{not json!"
    json.loads((cfg / "settings.json").read_text())  # now valid


def test_unknown_flag_exits_2(wave):
    r = run_install(wave, "--bogus")
    assert r.returncode == 2


def test_preset_file_is_valid_wave_widget_json():
    presets = json.loads(
        (REPO / "wave" / "config" / "widgets.shesh.json").read_text()
    )
    for key, widget in presets.items():
        assert key.startswith("shesh-")
        assert "display:name" in widget
        assert "blockdef" in widget and "meta" in widget["blockdef"]


def test_theme_is_valid_wave_termtheme():
    theme = json.loads(
        (REPO / "wave" / "config" / "termthemes" / "shesh-dark.json").read_text()
    )
    assert theme["display:name"].startswith("Shesh")
    for color in ("black", "red", "green", "blue", "white", "brightWhite"):
        assert theme[color].startswith("#") and len(theme[color]) == 7
