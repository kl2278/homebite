# Diet enforcement: before vs after

A head-to-head test with a general chatbot showed that a vegetarian preference only reached the AI as text: pork belly stayed in the recipe. Vegetarian, vegan and pescatarian are now checked by code (keyword list), trigger one substitution re-run, and are shown as NOT <diet> if a conflict remains. Any other preference (halal, kosher) is still only passed to the AI and is not verified. The Goal selector is not verified either.

## (a) Offline: the diet check on saved results (no LLM calls)

- Dishes without a dietary preference: 18 of 18 saved measurement results are unaffected (no diet check is computed; the saved example has none either: diet_check is None).

### False-alarm check: the vegetarian ratatouille runs (d08)

| Run | Adapted ingredients | Definite conflicts | Uncertain (check the label) |
|---|---|---|---|
| d08 baseline | eggplant, zucchini, tomatoes, red bell pepper, onion, garlic, olive oil, thyme, rosemary, basil, bay leaf, baguette | none | none |
| d08 cost_saver | eggplant, zucchini, red bell pepper, tomato, onion, garlic, olive oil, fresh thyme, bay leaf, bread flour, yeast | none | none |

### Every saved dish checked as if it were vegetarian (not real runs; shows what the keyword list catches)

| Run | Definite conflicts | Uncertain |
|---|---|---|
| d01 Taiwanese beef noodle soup | ['Beef shank'] | none |
| d02 Japanese chicken katsu curry | ['chicken breast'] | ['Worcestershire sauce'] |
| d03 Thai pad thai with shrimp | ['fish sauce'] | none |
| d04 Korean kimchi jjigae with tofu | ['Pork belly', 'Fish sauce'] | none |
| d05 Chinese tomato and egg stir-fry wi | none | none |
| d06 Italian spaghetti alla napoletana | none | none |
| d07 Indian chicken tikka masala with b | ['Chicken thigh'] | none |
| d08 French Provençal ratatouille with  | none | none |
| d09 Spanish paella with seafood, chick | ['chicken thigh', 'Great Value Boneless Skinless Chicken Breasts per lb', 'chicken broth'] | none |
| d10 Mexican guacamole & pico de gallo | none | none |

## (b) Live run: Korean kimchi jjigae, Walmart, vegetarian, goal lower sodium, 2 servings

- Status: complete; writer path: first_try; wall time 17.5 s (the app showed 17.4 s)
- Tokens: 11,306 input (2,159 cached, 4,404 cache-write), 3,854 output, 10 requests; cost $0.002973
- Tokens by stage (input, cached, output): {'guard': (336, 0, 34), 'intake': (315, 0, 173), 'analyst': (6376, 2159, 1651), 'substitution': (1661, 0, 546), 'substitution_rerun': (1875, 0, 943), 'writer': (743, 0, 507)}
- Diet check entries in the safety checks: Diet check: warning (conflict found: Pork belly (contains pork); re-running substitution once); Diet check (after re-run): passed (the conflicting ingredients were replaced or removed)
- Substitution re-run happened: yes
- Pork belly in the final adapted ingredient list: no; left out: ['Pork belly', 'Gochugaru', 'Dried anchovy', 'Kelp']
- 'pork' appears in the cooking steps: no
- Diet hard stop: False; uncertain items: [('Kimchi', 'traditional kimchi often contains fish sauce or shrimp; check the label')]

### What the student sees

- header: Kimchi jjigae at Walmart
- metrics: [('Substitutes found', '0'), ('Items left out', '4'), ('Allergen status', 'No allergies selected'), ('Run time', '17 s'), ('Est. cost', '$0.0030')]
- yellow box: Couldn't confirm these are vegetarian. Check the label. | - Kimchi: traditional kimchi often contains fish sauce or shrimp; check the label
- subheaders: Ingredients, Steps, What will taste different, Substitutions, Allergen check, Diet check, Nutrition per serving, Usage
- ingredients shown: - Kimchi: about 200 g; - Firm tofu: about 200 g; - Onion: about 60 g; - Scallions: about 20 g; - Garlic: about 8 g; - Sesame oil: about 6 g; - ~~Pork belly~~ (left out, no suitable substitute); - ~~Gochugaru~~ (left out, no suitable substitute); - ~~Dried anchovy~~ (left out, no suitable substitute); - ~~Kelp~~ (left out, no suitable substitute)
- steps shown: 1. Warm the sesame oil in a pot over medium heat. Add the kimchi, onion, and garlic, and cook until softened, stirring occasionally. 2. Add the tofu and gently stir to coat it in the kimchi mixture. Cover and simmer over low heat until the onion is tender and the flavors have come together. 3. Stir in the scallions just before serving.

Re-run proposals:

- Pork belly: no_substitute (No suitable item was returned from the Walmart catalog; pork must be omitted to keep the dish vegetarian.)
- Gochugaru: no_substitute (No suitable item was returned from the Walmart catalog.)
- Dried anchovy: no_substitute (No suitable vegetarian item was returned; skipping also avoids adding a potentially salty replacement.)
- Kelp: no_substitute (No suitable item was returned from the Walmart catalog.)

### Earlier result for the same settings (reported from the head-to-head test, not in the repo)

Pork belly (120 g) stayed in the recipe as a common item, the first step browned it, and only the Writer's intro said the version is not vegetarian.

