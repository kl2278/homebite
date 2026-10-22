"""Run the example once (live) and save it as the UI's saved example. Costs a few cents of tokens."""

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from agents import RunDeps, run_pipeline, save_result  # noqa: E402

settings = RunDeps(store="Walmart", allergies=["peanuts"], dietary_preferences=[], goals=[])
result = run_pipeline("Taiwanese beef noodle soup\nServings wanted: 2", settings, progress_callback=print)
save_result(result, "tests/fixtures/example_result.json")
print("status:", result.status, "| total tokens:", result.usage_total)
