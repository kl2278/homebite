"""Usage tracking: log every agent run and keep a running session total."""

import json
from datetime import datetime, timezone
from pathlib import Path

# True while the prices below are made-up placeholders. Set to False once they are real.
PRICES_ARE_PLACEHOLDER = True

# Edit these: price in USD per one million tokens.
INPUT_PRICE_PER_M = 1.00
CACHED_INPUT_PRICE_PER_M = 0.25
OUTPUT_PRICE_PER_M = 4.00

LOG_PATH = Path(__file__).resolve().parent / "logs" / "usage.jsonl"

# Running total for this session (in memory).
session_total = {
    "runs": 0,
    "input_tokens": 0,
    "cached_input_tokens": 0,
    "output_tokens": 0,
    "requests": 0,
    "estimated_cost_usd": 0.0,
}


def estimate_cost(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Cost in USD. input_tokens includes cached tokens, which are billed at the cached rate."""
    fresh = input_tokens - cached_tokens
    return (
        fresh * INPUT_PRICE_PER_M
        + cached_tokens * CACHED_INPUT_PRICE_PER_M
        + output_tokens * OUTPUT_PRICE_PER_M
    ) / 1_000_000


def record_run(agent_name: str, usage) -> dict:
    """Record one agent run from the RunUsage object PydanticAI returns (result.usage)."""
    cached = usage.cache_read_tokens or 0
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent_name,
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": usage.output_tokens,
        "requests": usage.requests,
        "estimated_cost_usd": round(
            estimate_cost(usage.input_tokens, cached, usage.output_tokens), 6
        ),
    }

    session_total["runs"] += 1
    session_total["input_tokens"] += entry["input_tokens"]
    session_total["cached_input_tokens"] += cached
    session_total["output_tokens"] += entry["output_tokens"]
    session_total["requests"] += entry["requests"]
    session_total["estimated_cost_usd"] += entry["estimated_cost_usd"]

    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry
