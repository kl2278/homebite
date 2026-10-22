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

## Prompt 1: skeleton and Portkey connection

````
Next, the project skeleton and the model connection. Build only what's listed here.

1. Find my working Portkey setup from Homework 5. It is in my Homework 5 folder, in backend/config.py (probably something like ../Homework 5/backend/config.py; look for the sibling folder). Read its build_model() and copy that exact pattern into this project: same provider, same gateway settings, and it must return OpenAIResponsesModel, because the chat completions endpoint rejected function tools for gpt-6-luna. If you can't access that folder, tell me and I'll paste the file. Do not copy any secret values.

2. Set up the environment: create .venv, and install pydantic-ai-slim with the OpenAI extra (check the current package name and extras), python-dotenv, streamlit, pandas, pytest. Write requirements.txt and .env.example (PORTKEY_API_KEY= and OPENAI_API_KEY=, empty). Run pip check.

3. Create llm.py (or config.py) with: the model name constant "gpt-6-luna"; a .env loader that checks the repo folder first and then the folder one level above (NOT the multi-level parent search from Homework 5); and build_model().

4. Create usage.py: record every agent run (agent name, input tokens, cached input tokens if the API reports them, output tokens, request count, estimated cost, timestamp) using the usage object PydanticAI returns, keep a running session total in memory, and append each run to logs/usage.jsonl. Put price-per-million-token constants at the top of the file for me to edit.

5. Create empty stubs for app.py, agents.py, tools.py, safety.py and a README.md placeholder. In agents.py, agents will be PydanticAI Agents with output_type set to Pydantic models and tools registered as plain Python functions. Don't implement them yet.

6. Write test_llm.py that makes ONE tiny real call through build_model() and prints the reply, the model name, and the token counts, never any key. Run it once with .env in this folder, then once with .env moved one level up (move it back afterwards), and show me both results.

7. Confirm gpt-6-luna is the only model name in the repo outside .venv, that .env is not staged, and commit "Prompt 1: skeleton and Portkey connection" including the AI_prompts.md entry.

Show me the test output and git status, then stop.
````
