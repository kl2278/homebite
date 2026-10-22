"""Shared test setup: keep test usage and safety logs out of the real logs/ folder."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import safety  # noqa: E402
import usage  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTKEY_API_KEY", "fake-key-for-tests")  # tests never call the real service; they use a fake model
    monkeypatch.setattr(usage, "LOG_PATH", tmp_path / "usage.jsonl")
    monkeypatch.setattr(safety, "SAFETY_LOG_PATH", tmp_path / "safety_events.jsonl")
