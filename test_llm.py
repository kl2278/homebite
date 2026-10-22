"""One tiny real call through build_model(). Run: python test_llm.py (never prints keys)."""

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # hide the startup banner

from pydantic_ai import Agent

from llm import MODEL_NAME, build_model

agent = Agent(build_model(), instructions="Answer in one short sentence.")
result = agent.run_sync("Say hello to a new student.")
usage = result.usage

print("Reply:", result.output)
print("Model:", MODEL_NAME)
print(
    f"Tokens: input={usage.input_tokens} cached={usage.cache_read_tokens} "
    f"output={usage.output_tokens} requests={usage.requests}"
)
