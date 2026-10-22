"""Usage tracking: log every agent run and keep a running session total."""

import json
from datetime import datetime, timezone
from pathlib import Path

# Real gpt-6-luna prices, in USD per 1M tokens.
# Source: course slides, "Cached Token Cost" slide, gpt-6-luna row.
PRICES_ARE_PLACEHOLDER = False
INPUT_PRICE_PER_M = 0.10
CACHED_INPUT_PRICE_PER_M = 0.01
CACHE_WRITE_PRICE_PER_M = 0.125  # 25% more than normal input
OUTPUT_PRICE_PER_M = 0.50
# Cache writes are priced above only if the provider reports them (usage.cache_write_tokens). If it reports 0,
# all non-cached input is priced at the normal input rate, so cost may be slightly underestimated.

LOG_PATH = Path(__file__).resolve().parent / "logs" / "usage.jsonl"

# Running total for this session (in memory).
session_total = {
    "runs": 0,
    "input_tokens": 0,
    "cached_input_tokens": 0,
    "cache_write_tokens": 0,
    "output_tokens": 0,
    "requests": 0,
    "estimated_cost_usd": 0.0,
}


def estimate_cost(input_tokens: int, cached_tokens: int, output_tokens: int, cache_write_tokens: int = 0) -> float:
    """Cost in USD. input_tokens includes cached and cache-write tokens, which have their own rates."""
    fresh = input_tokens - cached_tokens - cache_write_tokens
    return (
        fresh * INPUT_PRICE_PER_M
        + cached_tokens * CACHED_INPUT_PRICE_PER_M
        + cache_write_tokens * CACHE_WRITE_PRICE_PER_M
        + output_tokens * OUTPUT_PRICE_PER_M
    ) / 1_000_000


def record_run(agent_name: str, usage) -> dict:
    """Record one agent run from the RunUsage object PydanticAI returns (result.usage)."""
    cached = usage.cache_read_tokens or 0
    cache_write = usage.cache_write_tokens or 0
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": cached,
        "cache_write_tokens": cache_write,
        "output_tokens": usage.output_tokens,
        "requests": usage.requests,
        "estimated_cost_usd": round(
            estimate_cost(usage.input_tokens, cached, usage.output_tokens, cache_write), 6
        ),
    }

    session_total["runs"] += 1
    session_total["input_tokens"] += entry["input_tokens"]
    session_total["cached_input_tokens"] += cached
    session_total["cache_write_tokens"] += cache_write
    session_total["output_tokens"] += entry["output_tokens"]
    session_total["requests"] += entry["requests"]
    session_total["estimated_cost_usd"] += entry["estimated_cost_usd"]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
