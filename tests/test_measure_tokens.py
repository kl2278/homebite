"""Tests for the helpers in scripts/measure_tokens.py (no LLM calls)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import measure_tokens as m  # noqa: E402


def record(dish, config, latency, tokens, ts):
    stage = {"input": tokens, "cached": 0, "cache_write": 0, "output": 10, "requests": 1, "tool_calls": 0}
    return {"dish_id": dish, "config": config, "status": "ok", "latency_s": latency, "timestamp": ts, "stages": {"guard": stage}}


def test_percentile_and_mean():
    assert m.pct([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9.1
    assert m.mean([1, None, 3]) == 2


def test_gateway_cache_flags_catch_fast_runs_and_identical_tokens():
    runs = [record("d01", "baseline", 40, 1000, "2026-01-01T00:00:01"), record("d02", "baseline", 45, 1100, "2026-01-01T00:00:02"),
            record("d03", "baseline", 42, 1200, "2026-01-01T00:00:03"),
            record("d04", "baseline", 3, 1300, "2026-01-01T00:00:04"),   # far faster than the others
            record("d05", "baseline", 44, 1000, "2026-01-01T00:00:05")]  # same tokens as d01
    flags = m.flag_cache_hits(runs)
    assert flags[("d04", "baseline")] and flags[("d05", "baseline")]
    assert not flags[("d01", "baseline")] and not flags[("d02", "baseline")]


def test_cost_uses_the_price_constants_and_cache_write_rate(monkeypatch):
    import usage

    assert abs(usage.estimate_cost(1_000_000, 0, 0) - usage.INPUT_PRICE_PER_M) < 1e-9
    assert abs(usage.estimate_cost(1_000_000, 1_000_000, 0) - usage.CACHED_INPUT_PRICE_PER_M) < 1e-9
    assert abs(usage.estimate_cost(1_000_000, 0, 1_000_000) - (usage.INPUT_PRICE_PER_M + usage.OUTPUT_PRICE_PER_M)) < 1e-9
    assert abs(usage.estimate_cost(1_000_000, 0, 0, cache_write_tokens=1_000_000) - usage.CACHE_WRITE_PRICE_PER_M) < 1e-9
    assert (usage.INPUT_PRICE_PER_M, usage.CACHED_INPUT_PRICE_PER_M, usage.CACHE_WRITE_PRICE_PER_M, usage.OUTPUT_PRICE_PER_M) == (0.10, 0.01, 0.125, 0.50)
    assert usage.PRICES_ARE_PLACEHOLDER is False


def test_dish_list_matches_the_agreed_set():
    dishes = m.load_dishes()
    assert [d["id"] for d in dishes] == [f"d{i:02d}" for i in range(1, 11)]
    assert all(d["servings"] == 2 for d in dishes)
    assert sum(1 for d in dishes if d["expected_allergen_conflicts"]) == 5
