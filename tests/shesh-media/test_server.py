import shutil as _sh

from shesh_media.server import list_sinks, set_wallpaper, take_screenshot

# Strict-media semantics: no fabricated success when grim is absent (test_media.py
# covers the strict contract in depth; these legacy-name tests stay honest).


def test_screenshot():
    res = take_screenshot("/tmp/test_shesh.png")
    if _sh.which("grim"):
        assert res["ok"] is True
    else:
        assert res["ok"] is False and "grim" in res["error"]


def test_sinks():
    res = list_sinks()
    assert "sinks" in res


def test_wallpaper_missing():
    res = set_wallpaper("/nonexistent.jpg")
    assert res["ok"] is False
