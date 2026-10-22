"""Model connection: the model name, .env loading and the Portkey-routed model."""

import os
from pathlib import Path

from dotenv import dotenv_values

# The one and only model used by every agent.
MODEL_NAME = "gpt-6-luna"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PORTKEY_API_KEY_ENV = "PORTKEY_API_KEY"

REPO_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    """Load .env from the repo folder first, then the folder one level above.

    Values already set (or found in the first file) are not overridden.
    Empty values count as unset. Nothing is printed.
    """
    for folder in (REPO_DIR, REPO_DIR.parent):
        for key, value in dotenv_values(folder / ".env").items():
            if value and not os.environ.get(key):
                os.environ[key] = value


def build_model():
    """Create the Portkey-routed model used by every agent."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    load_env()
    key = os.environ.get(PORTKEY_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{PORTKEY_API_KEY_ENV} is not set (put it in .env).")
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=key,
        default_headers={"x-portkey-api-key": key},
    )
    # Chat completions rejected function tools for this model (HTTP 400); the Responses endpoint works.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
