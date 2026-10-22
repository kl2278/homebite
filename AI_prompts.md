# AI Prompts Log: HomeBite

Every prompt sent to the AI assistant, copied verbatim.

Template for each entry:

    ## <Prompt title>

    ```
    <prompt text, verbatim>
    ```

    **Follow-up / correction:** <one-line note on what went wrong>

    ```
    <follow-up text, verbatim>
    ```

---

## Setup: housekeeping

```
Before writing any code, set up the housekeeping for my final project. This folder is the project root (already created, don't make a nested folder). If it isn't a git repo yet, run git init.

1. Create CLAUDE.md in the project root recording everything below so it persists across sessions. State at the top that this CLAUDE.md takes priority over any CLAUDE.md in a parent folder, because parent files may contain outdated model names from earlier assignments.

PROJECT: "HomeBite", a solo final project for an AI agents class. It helps international students adapt dishes from home using ingredients available at their local grocery stores, with nutrition numbers computed in code from bundled USDA data (never invented by the model). Stack: Python, PydanticAI agents with Pydantic structured outputs, Streamlit UI.

RULES:
- Model: use ONLY "gpt-6-luna" through Portkey, with the PORTKEY_API_KEY env var. No other model name may appear anywhere in the code, comments or configs.
- Keys: the only env var names allowed are PORTKEY_API_KEY and OPENAI_API_KEY, spelled exactly. The app must look for .env first in the repo folder, then in the folder one level above it. Never read, print or copy values from .env (you may only check whether a variable is set). Keep .env.example with variable names only. Never commit .env.
- The repo will be PUBLIC on GitHub: never commit secrets.
- It must run locally from a fresh clone with `pip install -r requirements.txt` then `streamlit run app.py`. No other API keys, no live third-party APIs; all data ships in the repo under data/.
- Keep the code simple and readable.
- Work one prompt at a time. Do not build ahead of what I ask for.
- Commit once per prompt with a clear message. Do not push unless I ask.

PROMPT LOG RULE: Keep AI_prompts.md in the project root. After finishing each prompt I send you, append a section with a heading, then my prompt copied VERBATIM in a code block (do not reword, shorten or summarize it). When I send a follow-up or correction, add it under the same section with a one-line note on what went wrong. Include AI_prompts.md in that prompt's commit.

2. Create AI_prompts.md with a title and a short template, and log THIS prompt as the first entry ("Setup: housekeeping").
3. Create .gitignore (.env, .venv/, __pycache__/, .DS_Store, logs/) and make the first commit "Setup: CLAUDE.md and prompt log".

Confirm what you saved. Don't write any other code.
```
