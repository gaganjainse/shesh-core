"""Tests for display control and sandboxed document handling.

No hardware, no compositor, no container engine: the runner and the binary
lookup are injected everywhere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shesh_desktop_ctl import display as disp  # noqa: E402
from shesh_desktop_ctl import documents as docs  # noqa: E402
from shesh_desktop_ctl.display import Result  # noqa: E402

HAS_HYPR = lambda n: "/usr/bin/hyprctl" if n == "hyprctl" else None   # noqa: E731
HAS_WLR = lambda n: "/usr/bin/wlr-randr" if n == "wlr-randr" else None  # noqa: E731
HAS_PODMAN = lambda n: "/usr/bin/podman" if n == "podman" else None    # noqa: E731
NOTHING = lambda _n: None                                              # noqa: E731

MONITORS = json.dumps([{
    "name": "eDP-1", "description": "internal", "width": 1920, "height": 1200,
    "refreshRate": 144.0, "scale": 1.0, "x": 0, "y": 0, "focused": True,
    "disabled": False, "availableModes": ["1920x1200@144.00Hz", "1920x1080@60.00Hz"],
}, {
    "name": "DP-1", "description": "external", "width": 2560, "height": 1440,
    "refreshRate": 60.0, "scale": 1.0, "x": 1920, "y": 0, "focused": False,
    "disabled": False, "availableModes": ["2560x1440@60.00Hz"],
}])


def ok(stdout=""):
    return lambda cmd, **kw: Result(stdout, "", 0)


def capture(store, stdout=MONITORS):
    def runner(cmd, **kw):
        store.append(cmd)
        return Result(stdout, "", 0)
    return runner


# ── display: reading ────────────────────────────────────────────────────────

def test_monitors_parsed_from_hyprctl():
    r = disp.list_monitors(runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] and r["backend"] == "hyprctl"
    assert [m["name"] for m in r["monitors"]] == ["eDP-1", "DP-1"]
    assert r["monitors"][0]["refresh"] == 144.0


def test_wlr_randr_is_used_when_hyprctl_is_absent():
    out = "eDP-1 Foo\n  1920x1200 px, 144.000000 Hz (current)\n  1280x720 px, 60.000000 Hz"
    r = disp.list_monitors(runner=ok(out), which=HAS_WLR)
    assert r["ok"] and r["backend"] == "wlr-randr"
    assert r["monitors"][0]["width"] == 1920


def test_no_backend_is_reported_with_a_remedy():
    r = disp.list_monitors(runner=ok(), which=NOTHING)
    assert r["ok"] is False and "wlr-randr" in r["remedy"]


def test_malformed_json_is_not_fatal():
    r = disp.list_monitors(runner=ok("not json"), which=HAS_HYPR)
    assert r["ok"] is False and "JSON" in r["error"]


# ── display: writing is gated ───────────────────────────────────────────────

def test_mode_change_requires_confirmation():
    r = disp.set_mode("eDP-1", 1920, 1080, runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] is False and r["confirm_required"] is True


def test_mode_change_returns_the_previous_mode_so_it_can_be_restored():
    r = disp.set_mode("eDP-1", 1920, 1080, runner=ok(MONITORS), which=HAS_HYPR)
    assert r["previous"] == {"width": 1920, "height": 1200, "refresh": 144.0}


def test_unadvertised_mode_is_refused():
    """A mode the panel does not support can black the screen out."""
    r = disp.set_mode("eDP-1", 800, 600, confirm=True,
                      runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] is False
    assert "not advertised" in r["error"]
    assert "1920x1200" in r["available"]


def test_advertised_mode_is_applied_once_confirmed():
    calls = []
    r = disp.set_mode("eDP-1", 1920, 1080, 60, confirm=True,
                      runner=capture(calls), which=HAS_HYPR)
    assert r["ok"] is True
    assert any("1920x1080" in " ".join(c) for c in calls)


@pytest.mark.parametrize("name", ["a b", "x;rm -rf /", "$(id)", "../etc", ""])
def test_unsafe_monitor_names_are_refused(name):
    assert disp.set_mode(name, 1920, 1080, confirm=True,
                         runner=ok(MONITORS), which=HAS_HYPR)["ok"] is False
    assert disp.set_scale(name, 1.5, confirm=True,
                          runner=ok(MONITORS), which=HAS_HYPR)["ok"] is False


def test_unknown_monitor_is_refused():
    r = disp.set_mode("HDMI-9", 1920, 1080, confirm=True,
                      runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] is False and "no monitor" in r["error"]


@pytest.mark.parametrize("bad", [0, 0.1, 5, -1, "big", None])
def test_scale_is_bounded(bad):
    """Extreme scaling makes the interface unusable and hard to undo."""
    r = disp.set_scale("eDP-1", bad, confirm=True,
                       runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] is False


def test_scale_within_range_is_applied():
    r = disp.set_scale("eDP-1", 1.25, confirm=True,
                       runner=ok(MONITORS), which=HAS_HYPR)
    assert r["ok"] is True and r["current"]["scale"] == 1.25


def test_disabling_the_only_output_is_refused_outright():
    """Not merely confirmed: there would be no display left to undo it on."""
    single = json.dumps([json.loads(MONITORS)[0]])
    r = disp.set_enabled("eDP-1", False, confirm=True,
                         runner=ok(single), which=HAS_HYPR)
    assert r["ok"] is False and "only active output" in r["error"]


def test_disabling_a_second_output_is_allowed_with_confirmation():
    assert disp.set_enabled("DP-1", False, confirm=True,
                            runner=ok(MONITORS), which=HAS_HYPR)["ok"] is True


def test_enable_requires_confirmation():
    r = disp.set_enabled("DP-1", True, runner=ok(MONITORS), which=HAS_HYPR)
    assert r["confirm_required"] is True


# ── documents: validation before anything runs ──────────────────────────────

def test_missing_file_is_reported():
    assert docs.to_markdown("/nope.pdf", runner=ok(), which=HAS_PODMAN)["ok"] is False


def test_unsupported_type_lists_what_is_supported(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00")
    r = docs.to_markdown(str(f), runner=ok(), which=HAS_PODMAN)
    assert r["ok"] is False and ".pdf" in r["supported"]


def test_oversized_input_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "MAX_INPUT_BYTES", 10)
    f = tmp_path / "big.md"
    f.write_text("x" * 100)
    r = docs.to_markdown(str(f), runner=ok(), which=HAS_PODMAN)
    assert r["ok"] is False and "exceeds" in r["error"]


@pytest.mark.parametrize("part", [".ssh", ".gnupg", "Vaults", "Documents/Job"])
def test_protected_paths_are_refused(tmp_path, part):
    d = tmp_path / part
    d.mkdir(parents=True)
    f = d / "secret.md"
    f.write_text("private")
    r = docs.to_markdown(str(f), runner=ok(), which=HAS_PODMAN)
    assert r["ok"] is False and "protected" in r["error"]


def test_no_container_engine_is_reported(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("hello")
    r = docs.to_markdown(str(f), runner=ok(), which=NOTHING)
    assert r["ok"] is False and "container engine" in r["error"]


# ── documents: the sandbox contract ─────────────────────────────────────────

def _md(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# Title\n\nBody.\n")
    return f


def test_conversion_runs_isolated_and_unprivileged(tmp_path):
    calls = []
    docs.to_markdown(str(_md(tmp_path)),
                     runner=lambda c, **k: (calls.append(c), Result("# Title", "", 0))[1],
                     which=HAS_PODMAN)
    argv = calls[0]
    assert "--network=none" in argv, "a document never needs the network"
    assert "--cap-drop=ALL" in argv
    assert "--rm" in argv and "--read-only" in argv


def test_the_input_is_mounted_read_only(tmp_path):
    calls = []
    f = _md(tmp_path)
    docs.to_markdown(str(f),
                     runner=lambda c, **k: (calls.append(c), Result("x", "", 0))[1],
                     which=HAS_PODMAN)
    mount = [a for a in calls[0] if str(f) in a]
    assert mount and mount[0].endswith(":ro,Z"), "input must be read-only"


def test_markdown_conversion_returns_text(tmp_path):
    r = docs.to_markdown(str(_md(tmp_path)), runner=ok("# Title\n\nBody."),
                         which=HAS_PODMAN)
    assert r["ok"] is True and "Title" in r["text"]


def test_extraction_counts_what_it_found(tmp_path):
    r = docs.extract_text(str(_md(tmp_path)), runner=ok("one two three"),
                          which=HAS_PODMAN)
    assert r["ok"] is True and r["words"] == 3


def test_pdf_extraction_uses_pdftotext(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\n")
    calls = []
    docs.extract_text(str(f),
                      runner=lambda c, **k: (calls.append(c), Result("text", "", 0))[1],
                      which=HAS_PODMAN)
    assert "pdftotext" in calls[0]


def test_writing_requires_confirmation(tmp_path):
    r = docs.convert(str(_md(tmp_path)), "html", runner=ok("<h1/>"),
                     which=HAS_PODMAN)
    assert r["ok"] is False and r["confirm_required"] is True


def test_overwrite_requires_confirmation(tmp_path):
    src = _md(tmp_path)
    dest = tmp_path / "out.html"
    dest.write_text("existing")
    r = docs.convert(str(src), "html", str(dest), runner=ok("<h1/>"),
                     which=HAS_PODMAN)
    assert r["ok"] is False and "exists" in r["error"]
    assert dest.read_text() == "existing", "must not overwrite before confirming"


def test_confirmed_conversion_writes(tmp_path):
    src = _md(tmp_path)
    dest = tmp_path / "out.html"
    r = docs.convert(str(src), "html", str(dest), confirm=True,
                     runner=ok("<h1>Title</h1>"), which=HAS_PODMAN)
    assert r["ok"] is True and dest.read_text() == "<h1>Title</h1>"


def test_unsupported_target_is_refused(tmp_path):
    r = docs.convert(str(_md(tmp_path)), "exe", confirm=True,
                     runner=ok(), which=HAS_PODMAN)
    assert r["ok"] is False and "markdown" in r["supported"]


def test_conversion_failure_is_surfaced(tmp_path):
    r = docs.to_markdown(str(_md(tmp_path)),
                         runner=lambda c, **k: Result("", "pandoc: parse error", 1),
                         which=HAS_PODMAN)
    assert r["ok"] is False and "parse error" in r["error"]
