"""Offline tests for the shesh-files deterministic classifier."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "shesh_files" / "classifier.py"


def load():
    spec = importlib.util.spec_from_file_location("classifier", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(autouse=True)
def no_llm(monkeypatch, tmp_path):
    monkeypatch.setenv("SHESH_NO_LLM", "1")
    monkeypatch.setattr(load(), "HOME", tmp_path, raising=False)


def test_pdf_to_reference():
    mod = load()
    r = mod.decide(str(mod.HOME / "report.pdf"))
    assert r["dest"].endswith("Documents/Reference")
    assert r["method"] == "rule"


def test_invoice_to_finance():
    mod = load()
    r = mod.decide(str(mod.HOME / "invoice_2026.pdf"))
    assert r["dest"].endswith("Documents/Personal/Finance")


def test_screenshot():
    mod = load()
    r = mod.decide(str(mod.HOME / "Screenshot from 2026.png"))
    assert r["dest"].endswith("Media/Screenshots")


def test_gguf_to_models():
    mod = load()
    r = mod.decide(str(mod.HOME / "phi4-mini-q4.gguf"))
    assert r["dest"].endswith("AI/Models")


def test_unknown_low_confidence_under_home():
    mod = load()
    r = mod.decide(str(mod.HOME / "weird.xyz123"))
    assert r["dest"].startswith(str(mod.HOME))
    assert r["conf"] <= 0.3
