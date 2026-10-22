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

## Prompt 2: data layer and tools

````
Next, the data layer and tools. No agents and no LLM calls in this step. Build only what's listed here.

1. data/nutrition.csv: a compact nutrition table (per 100 g) built from USDA FoodData Central public-domain data (SR Legacy / Foundation Foods). Write scripts/build_nutrition.py that downloads the official USDA CSV, keeps roughly 1,500-3,000 common foods, and keeps only: fdc_id, description, kcal, protein_g, fat_g, carbs_g, fiber_g, sugar_g, sodium_mg. Make sure staples common in East Asian, South Asian, Latin American, Middle Eastern and European cooking are included (tofu, bok choy, daikon, rice varieties, noodles, soy sauce, miso, lentils, chickpeas, tortillas, yogurt, olive oil, common cheeses, etc.). [OPTIONAL: my home cuisine is ___, so make sure its staples are covered.] Commit the resulting CSV so the app never needs to download anything. If the download is blocked, tell me exactly which file to download and where to put it. Never invent nutrition numbers.

2. data/grocery_catalog.csv: columns store, product_name, category, usda_match_description (must exactly match a description in nutrition.csv), allergen_tags (semicolon-separated from: peanuts, tree_nuts, shellfish, fish, soy, wheat_gluten, eggs, dairy, sesame; empty if none), price_usd, verified (true/false, default false), source_note. Build a starter catalog of about 150 realistic items across: Walmart, Trader Joe's, Whole Foods, Aldi, "Asian grocery". Add data/README.md stating clearly that this is a starter set for demo purposes, prices are illustrative and not current, and that I will check entries against real store listings and set verified=true only for items I confirm. Write a test that every usda_match_description exists in nutrition.csv.

3. tools.py: plain Python functions with full type hints and clear docstrings (they will be registered as PydanticAI tools in the next step, so the docstrings and parameter names matter). Return Pydantic models or plain dicts, always with a "found" flag where relevant:
   - search_nutrition(query: str, limit: int = 5): fuzzy match against nutrition.csv; return fdc_id, description and per-100g values.
   - search_catalog(ingredient_query: str, store: str, exclude_allergens: list[str] = []): matching items at that store, excluding listed allergens; include price and verified flag.
   - compute_recipe_nutrition(ingredients: list of {fdc_id, grams}, servings: int): per-serving totals computed IN CODE, never by a model. Report any ingredient whose fdc_id was not found instead of silently skipping it.
   - check_allergens(ingredients: list of names or catalog items, allergens: list[str]): return conflicts, plus an "uncertain" list for ingredients whose allergen status can't be determined from the catalog tags or the keyword list. Missing data must never be reported as safe.
   Use the standard library for fuzzy matching (e.g. difflib) unless it is clearly inadequate; if you add a dependency, update requirements.txt.

4. tests/test_tools.py with pytest covering: each tool's normal case, a not-found query that returns found=False instead of guessing, an allergen conflict (e.g. peanut), an "uncertain" allergen case, and a nutrition computation checked by hand against known values.

5. Run the tests and show me they pass. Then follow the prompt-log rule from CLAUDE.md, confirm .env is not staged, and commit "Prompt 2: data layer and tools". Don't push.

Show me: the row counts for both CSVs, a few sample rows of each, the test results, and git status. Then stop.
````

## Prompt 3: agents and pipeline

````
Now the agents. Build only what's listed here. This step makes real LLM calls, so keep test runs few.

1. Two small data/tool fixes first:
   a. In tools.py, the allergen keyword "nut" matches words like "nutmeg". Make keyword matching word-based (for example, match whole words or a curated list such as almond, walnut, pecan, cashew, pistachio, hazelnut, macadamia, "peanut"), keep it conservative for real nuts, and add tests: nutmeg is not flagged, almond is.
   b. Check whether these foods exist in the full USDA SR Legacy download but were dropped by my filters in scripts/build_nutrition.py: raw chicken breast (meat only), glutinous rice (raw), and also ground beef raw, pork shoulder raw, salmon raw, shrimp raw, egg noodles, and rice noodles. If they exist, change the build script to always keep them (a must-include list), rebuild nutrition.csv, and update catalog entries that used fallbacks. If USDA really has no entry, say so. Don't invent numbers. Make sure all tests still pass.

2. In agents.py, build five stages with plain Python orchestration, using PydanticAI Agents with output_type set to Pydantic models. Use build_model() for the model. Define a RunDeps dataclass (store, allergies, dietary preferences, goals) passed as deps. Register tools via PydanticAI as thin wrappers around the functions in tools.py. The wrapper for search_catalog must take store and exclude_allergens from RunDeps, NOT from the model's arguments, so the model can't search the wrong store or drop an allergy.

   - Intake Agent (no tools): turns the student's free text plus the sidebar settings into a structured Request: dish_name, cuisine_origin, servings, goals. Its output type is a union: either a Request or a ClarifyingQuestion (one question) when the dish is too vague to work with. Don't guess.
   - Dish Analyst Agent (tool: search_nutrition): breaks the dish into ingredients with approximate grams per serving. For each ingredient: role (flavor base / protein / starch / sauce / texture), a flag hard_to_find_abroad, and an fdc_id found via search_nutrition (null if no good match; never invent an id).
   - Substitution Agent (tools: search_catalog, search_nutrition): only for ingredients flagged hard_to_find_abroad. For each, choose the best product that actually comes back from search_catalog at the chosen store. For every choice, give a one-line taste/texture note and a one-line reason. If nothing suitable exists, say so honestly with status "no_substitute" and offer the closest option or a "skip it" suggestion. Cap its tool calls using PydanticAI usage limits (check the current docs for the right UsageLimits settings) at 6 tool calls per run.
   - Verifier (PURE CODE, no LLM): validate in code that each chosen substitute exists in grocery_catalog.csv for the chosen store (otherwise downgrade it to no_substitute); build the original and adapted ingredient lists (ingredients not flagged hard_to_find_abroad are kept as-is and labeled "common item, not checked against the catalog"); map to fdc_ids; call compute_recipe_nutrition for both versions; call check_allergens on the adapted list. Output a side-by-side comparison per serving. Every number must come only from tool results. List any ingredients that could not be matched to USDA data instead of dropping them silently.
   - Writer Agent (no tools): receives the Verifier output and writes a warm, concise answer for a student: a short intro, cooking steps, and a short "what will taste different" note. It must NOT state any nutrition number. Code renders the ingredient list, substitutions table and nutrition table from the Verifier data.

3. Control flow: Intake -> Analyst -> Substitution -> Verifier -> Writer, in a function run_pipeline(user_text, settings) that returns a PipelineResult. If Intake returns a ClarifyingQuestion, stop and return it. Record every agent run in the usage tracker with the agent name.

4. The PipelineResult must include a full trace: for each stage, a short input summary, each tool call (name, arguments, short result summary), the structured output, and token usage. Pull tool calls from the PydanticAI run messages.

5. Create run_example.py that runs one example end to end ("Taiwanese beef noodle soup", store Walmart, allergy peanuts) and prints the trace, the final answer and the token totals per stage. Then run it once with a deliberately vague input ("something from home") to show the clarifying-question path. Fix issues until both work, keeping the number of real runs small.

6. Follow the prompt-log rule from CLAUDE.md, confirm gpt-6-luna is still the only model name and .env is not staged, and commit "Prompt 3: agents and pipeline". Don't push.

Show me: the test results, the full output of both runs, token totals per stage, and git status. Then stop.
````

## Prompt 4: Streamlit UI

````
Now the Streamlit UI. Build only what's listed here. Real LLM calls cost tokens, so use the saved-fixture mode below while iterating on the layout, and make only a few live runs.

0. Small prerequisite changes (these are the ONLY changes allowed to agents.py and usage.py in this step):
   a. Add an optional progress_callback argument to run_pipeline(user_text, settings, progress_callback=None). It is called with a short stage label before each stage ("Reading your request", "Analyzing the dish", "Finding substitutes at your store", "Verifying nutrition and allergens", "Writing your recipe").
   b. Add a way to save a PipelineResult to JSON and load it back (Pydantic model_dump_json / model_validate_json is fine). Save the result of one good live run to tests/fixtures/example_result.json and commit it.
   c. In usage.py add PRICES_ARE_PLACEHOLDER = True at the top (I will flip it to False once I have real prices).

1. app.py layout:
   - Title "HomeBite", one-line description: adapt a dish from home using ingredients you can actually buy near you, with nutrition numbers computed from USDA data.
   - Sidebar: store selector (Walmart, Trader Joe's, Whole Foods, Aldi, Asian grocery), allergy multiselect (peanuts, tree nuts, shellfish, fish, soy, wheat/gluten, eggs, dairy, sesame), dietary preference selector, servings (1-8), and goal selector (none, higher protein, lower sodium, lower calorie).
   - A collapsed "Developer tools" expander in the sidebar with a toggle "Use saved example (no live AI call)", which loads tests/fixtures/example_result.json. When active, show a clear banner "Showing a saved example, no live AI call was made."
   - Main area: a text box "Tell me about a dish from home", three clickable example dishes from different cuisines (Taiwanese beef noodle soup, a French weekday lunch, an Indian dal), and a primary "Adapt my dish" button.
   - While running, show progress using the progress_callback (st.status or a spinner with the stage label).

2. Flow and state:
   - Use st.session_state so reruns (changing a widget, expanding a section) never repeat paid LLM calls. Store the PipelineResult and the inputs it was made with.
   - If Intake returns a ClarifyingQuestion, show it and a text input for the answer; on submit, combine the original text and the answer and run again.
   - Handle errors gracefully: a friendly message plus a "Try again" button, never a raw traceback.

3. Results (render from the PipelineResult only, do not call any model here):
   - Heading with the dish name and the store.
   - Writer's intro, then the adapted ingredient list, then the cooking steps and the "what will taste different" note.
   - Substitutions table: original -> substitute, store, price, taste/texture note, with a status column (substituted / no_substitute / common item, not checked against the catalog). Show prices as "starter catalog price, not live" in a caption.
   - Allergen status box: red (st.error) for conflicts; yellow (st.warning) listing uncertain ingredients with "Couldn't confirm these are free of <allergen>. Check the label."; green (st.success) only when all_clear, with the caption "Based on catalog tags and a keyword list, not a guarantee."
   - Nutrition: original vs adapted per serving. Use st.metric for calories and sodium with the delta, a st.bar_chart (or similar) for protein, fat, carbs, fiber, sugar in grams, and a caption listing ingredients NOT counted because USDA has no entry ("Totals exclude: ...; actual values are likely a bit higher").
   - An expander "How this was made" showing the trace stage by stage: which agent ran, which tools it called (name, arguments, short result), and what it returned, plus tokens per stage.
   - A "Usage" panel: tokens (input, cached, output) and estimated cost for this run and the session total, as a small table. If PRICES_ARE_PLACEHOLDER is True, caption it "Estimated cost uses placeholder prices."
   - Footer: nutrition values come from USDA FoodData Central; this is not medical advice; grocery data is a starter set.

4. Style: clean and simple. Use a page title/icon, st.columns for the side-by-side nutrition, consistent spacing, and no clutter. A person who has never seen the app should know what to do within 5 seconds.

5. Run it: start the app, test the saved-fixture mode first, then do ONE live run ("Taiwanese beef noodle soup", Walmart, peanuts) to check the end-to-end flow, including the Writer's text. Then test the vague-input path ("something from home"). Show me what each screen shows (describe it; I will take the screenshots myself). Fix problems you find.

6. Follow the prompt-log rule from CLAUDE.md, confirm gpt-6-luna is still the only model name and .env is not staged, and commit "Prompt 4: Streamlit UI". Don't push.

Give me: the exact command to run the app, a description of each screen, the live-run output (including any text the Writer produced about small amounts), 3 look-and-feel improvements you recommend, and git status. Then stop.
````
