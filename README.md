# HomeBite

Adapt a dish from home to ingredients you can actually buy at your local store.

HomeBite is for international students who miss the food from home but shop at a US grocery store. You describe a dish
(for example "Taiwanese beef noodle soup"), pick your store and any allergies, and HomeBite lists the ingredients,
suggests substitutes that really exist in that store's catalog, writes the cooking steps, and compares the nutrition of
the original and the adapted dish. The nutrition numbers are computed in code from bundled USDA data; the AI model never
invents them.

It is a solo final project for an AI agents class. It runs on your own computer; it is not hosted online.

## Run it (about 5 minutes)

You need Python and a `.env` file with a Portkey API key (see [.env](#env) below). Tested with Python 3.14.7 on macOS.

**macOS / Linux**

1. `git clone https://github.com/kl2278/homebite.git` and `cd` into the folder.
2. `python3 -m venv .venv`
3. `source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. Create the `.env` file (next section). Quick way: `cp .env.example .env`, then paste your key after `PORTKEY_API_KEY=`.
6. `streamlit run app.py`
7. Open the local URL Streamlit prints, normally http://localhost:8501 (it usually opens by itself).

**Windows (PowerShell)**

1. `git clone https://github.com/kl2278/homebite.git` and `cd` into the folder.
2. `py -m venv .venv`
3. `.venv\Scripts\Activate.ps1`
4. `pip install -r requirements.txt`
5. `copy .env.example .env`, then paste your key after `PORTKEY_API_KEY=`.
6. `streamlit run app.py`
7. Open http://localhost:8501.

The Windows steps follow the same commands but were not tested on a Windows machine. No other API keys, no live third-party services: all data ships in the repo under `data/`.

## .env

The app looks for `.env` **first in the repo folder, then in the folder one level above it**:

```
some-folder/
├── .env              <- found here if it is not in the repo folder
└── homebite-repo/
    ├── .env          <- looked at first
    ├── app.py
    └── ...
```

The only variable names are `PORTKEY_API_KEY` (used) and `OPENAI_API_KEY` (listed in `.env.example` but not used).
`.env.example` has the names only. `.env` is git-ignored: never commit it. The app only checks that the key is set;
it never prints it. Model: `gpt-6-luna`, called through Portkey.

If the key is missing, the page shows a short message saying where to put `.env`. The saved example (below) still works.

## Try it in 60 seconds

1. Click one of the three example buttons (Taiwanese beef noodle soup, French weekday lunch, Indian dal), then **Adapt my dish**.
   A run takes about 30 seconds.
2. Allergy test: in the sidebar select **peanuts**, type `Kung pao chicken`, and click **Adapt my dish**.
   Peanuts are flagged as a definite conflict and removed, or the recipe is shown as NOT safe. It is never shown as safe.
3. No key or no time? Open **Developer tools** in the sidebar and switch on **Use saved example (no live AI call)**.
   It shows a saved run with no LLM call and no cost.

## What's inside

| Path | What it is |
|---|---|
| `app.py` | The Streamlit page. Renders results only; it makes no model calls itself. |
| `agents.py` | The five-stage pipeline (PydanticAI agents with Pydantic outputs) and the code-only Verifier. |
| `tools.py` | Plain Python tools: USDA search, catalog search, recipe nutrition math, allergen check. |
| `safety.py` | Input screening, usage caps, output checks. All limits are named constants at the top. |
| `usage.py` | Records tokens and estimated cost of every agent run (course price slide). |
| `llm.py` | Model name, `.env` loading, the Portkey connection. |
| `data/` | `nutrition.csv` (USDA), `grocery_catalog.csv` (starter catalog), `measurement_dishes.json`. See `data/README.md`. |
| `scripts/` | `build_nutrition.py`, `safety_demo.py`, `measure_tokens.py`, `allergen_fix_check.py`. |
| `tests/` | The pytest suite and the saved example (`tests/fixtures/example_result.json`). |
| `logs/` | Committed evidence files (see below); everything else in `logs/` is git-ignored. |
| `AI_prompts.md` | Every prompt used to build this project, verbatim. |

The five stages:

1. **Intake** turns the text and sidebar settings into a structured request, or asks one clarifying question.
2. **Analyst** breaks the dish into ingredients with weights, flags the ones hard to find abroad, and looks up USDA entries.
3. **Substitution** picks substitutes that really come back from the catalog search at your store.
4. **Verifier** (pure code, no AI) checks the substitutes exist, computes nutrition for both versions and runs the allergen check.
5. **Writer** writes the intro, steps and "what will taste different" note, without any nutrition numbers.

## Tests and evidence

- `python -m pytest -q` runs the whole suite (about 190 tests). It uses a fake model and spends no tokens.
- `python test_llm.py` makes one tiny real call to check your key and connection.
- `python scripts/safety_demo.py` runs each safety defense and prints PASS/FAIL. Mostly free; the classifier cases and one full
  kung pao chicken run make real calls (about 3 cents). Output: `logs/safety_demo_output.txt`.
- `python scripts/measure_tokens.py` measures 10 dishes x 2 configs = 20 live runs (about 4 cents). It saves after every run and
  can resume. `--dry-run` uses a fake model (free); `--summarize-only` rebuilds the reports from saved runs without any call.
- `python scripts/allergen_fix_check.py` re-checks saved results with the current allergen keywords (one optional live run;
  `--offline-only` makes none).

Committed evidence files: `logs/safety_demo_output.txt`, `logs/token_report.csv`, `logs/token_summary.md`,
`logs/cost_experiment.md`, `logs/allergen_fix_check.md`.

## Data

- `data/nutrition.csv` is built from USDA FoodData Central **SR Legacy** (public domain), 3,000 common foods, per 100 g.
  A blank cell means USDA has no value (it is not zero).
- `data/grocery_catalog.csv` is a **starter set** of 163 items for five stores. Product names and prices are illustrative,
  not live store data. Every row has `verified=false` unless the maintainer has checked it against a real listing.
- Both files are small enough to ship in full, so there is no separate test dataset or switch.

## Known limits

- The catalog has only about 163 items, so the app often answers "no substitute" and leaves an ingredient out.
- Some ingredients have no USDA entry. They are left out of the nutrition totals, and the app says which ones.
- Allergen checks use catalog tags and a keyword list. They are not a guarantee: always read the real label.
- This is not medical advice.
- A run takes about 30 seconds.
- Prices and costs are estimates from the course pricing slide (gpt-6-luna), not an invoice.
- The Goal selector (for example lower sodium) is passed to the AI as context but is not enforced or verified by code, and the results page does not say whether the goal was met. Allergies and store are enforced by code; goals are not.
- Nutrition differences between the original and the adapted dish mostly reflect ingredients that were left out or have no USDA entry, not a healthier recipe. Treat the comparison as a consistency check on the ingredient list, not as a health claim.
- Allergies accept several selections; dietary preference and goal accept one choice each.

## Safety in one paragraph

Before any model runs, free input rules block instruction overrides, requests for the prompt or keys, and attempts to change the
store or allergies through the text; one cheap classifier call then screens for injection, medical advice, extreme dieting and
off-topic text, and fails closed if it cannot run. Sidebar settings are passed as trusted configuration, never as part of the
student's text. Spend is capped per agent, per run, per session, per day (read from the usage log) and per hour (rate limit).
After the Writer, an output check rejects leaked prompts, key-like strings, invented numbers, nutrition claims and unconfirmed
product names, retries once, then falls back to a plain template. If the allergen check finds a definite conflict, the substitution
stage is re-run once; if a conflict remains, the recipe is shown only as "NOT safe" for that allergen.
