# Allergen keyword fix: before vs after

The measurement (Prompt 6) found panko kept in a gluten-allergy recipe because `check_allergens` had no keyword for it. The keyword list was extended (see `EXTRA_ALLERGEN_KEYWORDS` in tools.py). The measurement files in `logs/measurement/` and the three measurement reports were taken with the OLD list and are unchanged.

## (a) Offline: saved measurement results re-checked with the new keywords (no LLM calls)

| Dish | Config | Allergy | Before (recorded) | After (new keywords) | Changed |
|---|---|---|---|---|---|
| d01 Taiwanese beef noodle soup | baseline | peanuts | 0 conflict(s) [], 4 uncertain, all_clear=False | 0 conflict(s) [], 4 uncertain, all_clear=False | no |
| d01 Taiwanese beef noodle soup | cost_saver | peanuts | 0 conflict(s) [], 5 uncertain, all_clear=False | 0 conflict(s) [], 5 uncertain, all_clear=False | no |
| d02 Japanese chicken katsu curry | baseline | wheat_gluten | 0 conflict(s) [], 6 uncertain, all_clear=False | 1 conflict(s) ['panko'], 5 uncertain, all_clear=False | **yes** |
| d02 Japanese chicken katsu curry | cost_saver | wheat_gluten | 0 conflict(s) [], 3 uncertain, all_clear=False | 1 conflict(s) ['Panko breadcrumbs'], 2 uncertain, all_clear=False | **yes** |
| d03 Thai pad thai with shrimp | baseline | shellfish | 0 conflict(s) [], 9 uncertain, all_clear=False | 0 conflict(s) [], 9 uncertain, all_clear=False | no |
| d03 Thai pad thai with shrimp | cost_saver | shellfish | 0 conflict(s) [], 9 uncertain, all_clear=False | 0 conflict(s) [], 9 uncertain, all_clear=False | no |
| d05 Chinese tomato and egg stir- | baseline | eggs | 0 conflict(s) [], 1 uncertain, all_clear=False | 0 conflict(s) [], 1 uncertain, all_clear=False | no |
| d05 Chinese tomato and egg stir- | cost_saver | eggs | 0 conflict(s) [], 1 uncertain, all_clear=False | 0 conflict(s) [], 1 uncertain, all_clear=False | no |
| d07 Indian chicken tikka masala  | baseline | dairy | 0 conflict(s) [], 3 uncertain, all_clear=False | 0 conflict(s) [], 3 uncertain, all_clear=False | no |
| d07 Indian chicken tikka masala  | cost_saver | dairy | 0 conflict(s) [], 4 uncertain, all_clear=False | 0 conflict(s) [], 4 uncertain, all_clear=False | no |
| d09 Spanish paella with seafood, | baseline | shellfish | 0 conflict(s) [], 2 uncertain, all_clear=False | 0 conflict(s) [], 2 uncertain, all_clear=False | no |
| d09 Spanish paella with seafood, | cost_saver | shellfish | 0 conflict(s) [], 2 uncertain, all_clear=False | 0 conflict(s) [], 2 uncertain, all_clear=False | no |
| d10 Mexican guacamole & pico de  | baseline | tree_nuts | 0 conflict(s) [], 0 uncertain, all_clear=True | 0 conflict(s) [], 0 uncertain, all_clear=True | no |
| d10 Mexican guacamole & pico de  | cost_saver | tree_nuts | 0 conflict(s) [], 1 uncertain, all_clear=False | 0 conflict(s) [], 1 uncertain, all_clear=False | no |

2 of 14 saved results changed. Each saved result is the FINAL recipe of the old run, so a recipe that now shows a conflict is one that the old check would have let through; in a new run it would trigger the substitution re-run.

## (b) Live run: d02 Japanese chicken katsu curry, Whole Foods, gluten allergy, baseline config

- Status: ok, latency 19.18 s, writer path: first_try
- First-pass conflicts (new keywords): ['panko', 'all-purpose flour', 'soy sauce']
- Panko detected as a definite conflict: **yes**
- Substitution re-run happened: **yes**
- Final adapted ingredients: ['chicken breast', 'white rice', 'egg', 'vegetable oil', 'onion', 'carrot', 'potato', 'garlic', 'ginger', 'curry powder', 'butter', 'apple', 'Worcestershire sauce', 'honey']
- Left out of the final recipe: ['panko', 'all-purpose flour', 'soy sauce']
- Final check: 0 conflict(s) [], 5 uncertain, all_clear=False; hard stop: False
- Panko still in the final recipe: **no**

Re-run proposals:

- panko: no_substitute (No suitable gluten-free panko substitute was found in the Whole Foods catalog; do not use wheat panko.)
- all-purpose flour: no_substitute (No suitable gluten-free flour substitute was found in the Whole Foods catalog; do not use wheat flour.)
- soy sauce: no_substitute (No gluten-free soy sauce was found; the listed tamari product was not confirmed safe for a wheat-gluten allergy.)

### What the student sees

- header: Japanese chicken katsu curry at Whole Foods
- yellow box: Couldn't confirm these are free of wheat gluten. Check the label. | - egg | - vegetable oil | - curry powder | - butter | - Worcestershire sauce
- ingredients shown: - chicken breast: about 300 g; - white rice: about 160 g; - egg: about 50 g; - vegetable oil: about 30 g; - onion: about 100 g; - carrot: about 50 g; - potato: about 100 g; - garlic: about 4 g; - ginger: about 4 g; - curry powder: about 10 g; - butter: about 16 g; - apple: about 30 g; - Worcestershire sauce: about 8 g; - honey: about 6 g; - ~~panko~~ (left out, no suitable substitute); - ~~all-purpose flour~~ (left out, no suitable substitute); - ~~soy sauce~~ (left out, no suitable substitute)

### Safety checks

- Usage limits: passed (rate limit 20 runs/hour, session cap, daily cap)
- Input rules: passed 
- Input classifier (guard): passed (ok: This is a request for a Japanese chicken katsu curry dish.)
- Allergen check: warning (conflict found: panko (wheat_gluten), all-purpose flour (wheat_gluten), soy sauce (wheat_gluten); re-running substitution once)
- Allergen check (after re-run): passed (the conflicting ingredients were replaced or removed)
- Output check: passed (Writer text passed)
- Usage limits (end of run): passed (12,957 tokens this run, under the 100,000 cap)

### Tokens and cost of this live run (new keywords) vs the old d02 baseline run

| Run | Input | Cached | Cache write | Output | Requests | Cost |
|---|---|---|---|---|---|---|
| old (measurement) | 8,356 | 0 | 4,726 | 3,079 | 7 | $0.002493 |
| new (this check) | 9,866 | 0 | 5,951 | 3,091 | 8 | $0.002681 |

One run each, so the difference in tokens is mostly the normal variation of the model, not an effect of the fix.

## Result

Panko is now a definite conflict. It was removed or replaced by the re-run.

