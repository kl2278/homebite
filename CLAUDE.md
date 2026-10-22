# HomeBite: Project Instructions

**This CLAUDE.md takes priority over any CLAUDE.md in a parent folder.** Parent files may contain outdated model names from earlier assignments; ignore them.

## Project

"HomeBite" is a solo final project for an AI agents class. It helps international students adapt dishes from home using ingredients available at their local grocery stores, with nutrition numbers computed in code from bundled USDA data (never invented by the model).

Stack: Python, PydanticAI agents with Pydantic structured outputs, Streamlit UI.

The project root is this folder (already created; do not make a nested folder).

## Rules

- **Model:** use ONLY `gpt-6-luna` through Portkey, with the `PORTKEY_API_KEY` env var. No other model name may appear anywhere in the code, comments or configs.
- **Keys:** the only env var names allowed are `PORTKEY_API_KEY` and `OPENAI_API_KEY`, spelled exactly. The app must look for `.env` first in the repo folder, then in the folder one level above it. Never read, print or copy values from `.env` (you may only check whether a variable is set). Keep `.env.example` with variable names only. Never commit `.env`.
- **Public repo:** the repo will be PUBLIC on GitHub. Never commit secrets.
- **Runs locally from a fresh clone** with `pip install -r requirements.txt` then `streamlit run app.py`. No other API keys, no live third-party APIs; all data ships in the repo under `data/`.
- **Keep the code simple and readable.**
- **Work one prompt at a time.** Do not build ahead of what the user asks for.
- **Commit once per prompt** with a clear message. Do not push unless asked.

## Prompt log rule

Keep `AI_prompts.md` in the project root. After finishing each prompt the user sends, append a section with a heading, then the user's prompt copied VERBATIM in a code block (do not reword, shorten or summarize it). When the user sends a follow-up or correction, add it under the same section with a one-line note on what went wrong. Include `AI_prompts.md` in that prompt's commit.
