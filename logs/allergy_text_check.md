# Allergy stated in the text, not selected in the sidebar: before and after

Found by my own manual test before recording the demo video: with the sidebar Allergies box empty and store Walmart, I typed `I want to make kung pao chicken, but I am allergic to peanuts.` and clicked Adapt. The live run returned a recipe with 30 g of peanuts and 16 g of peanut oil. This file is generated offline (no live calls, no tokens) by `scripts/allergy_text_check.py`.

## Before: the text above, nothing selected (fake model that answers like the live run)

- status: complete; AI calls made: 5 (guard classifier, Intake, Analyst, Substitution, Writer)
- ingredients in the recipe: white rice 100 g, peanuts 30 g, peanut oil 16 g, egg 50 g
- allergen check: no conflicts reported, because no allergy was selected (conflicts: 0)
- notices shown: blue medical banner (medical_context=True); lower on the page, "You didn't select any allergies, so no allergen check was run."

## After: the same text through the app's real button path

- AI calls made: 0 (the pipeline was replaced by a function that fails if called)
- tokens spent: 0 (usage log written: False)
- safety events written: 1: category `allergy_in_text`, caught by `rule`
- message shown (blue info box):

> You mentioned peanuts as an allergy or something to avoid. HomeBite only checks the allergies selected in the sidebar. Please select peanuts under Allergies, then describe your dish again.

Result: **PASS**

## Same text with Peanuts selected in the sidebar

- blocked: False (the request proceeds normally, as before the fix)

## An allergy outside the nine sidebar categories

- blocked: False; warning shown above the results: "You mentioned an allergy to kiwi and mango. HomeBite cannot check for it. Please check every ingredient and label yourself."

## Statements that stop the request when the allergen is not selected

| Text | Allergens found | Stopped |
|---|---|---|
| kung pao without peanuts | peanuts | yes |
| gluten-free ramen | wheat_gluten | yes |
| I can't eat shrimp or eggs | shellfish, eggs | yes |
| dairy free curry | dairy | yes |
| no sesame please | sesame | yes |
| I react to fish | fish | yes |
| I have celiac disease | wheat_gluten | yes |
| I'm lactose intolerant | dairy | yes |
| I have a tree nut allergy | tree_nuts | yes |
| I'm allergic to soy | soy | yes |

## False-alarm check: these must pass (nothing selected)

| Text | Allergens found | Passes |
|---|---|---|
| Taiwanese beef noodle soup | - | yes |
| Croque monsieur, a French weekday lunch | - | yes |
| Indian tadka dal with rice | - | yes |
| Japanese chicken katsu curry | - | yes |
| Thai pad thai with shrimp | - | yes |
| Korean kimchi jjigae with tofu | - | yes |
| Chinese tomato and egg stir-fry with rice | - | yes |
| Italian spaghetti alla napoletana | - | yes |
| Indian chicken tikka masala with basmati rice | - | yes |
| French Provençal ratatouille with a baguette | - | yes |
| Spanish paella with seafood, chicken, and vegetables | - | yes |
| Mexican guacamole & pico de gallo | - | yes |
| Mexican chicken tinga tacos with crema and queso fresco | - | yes |
| eggplant parmesan with butternut squash | - | yes |
| nutmeg cookies | - | yes |
| Thai green curry with coconut milk | - | yes |
| free range chicken soup | - | yes |
| kung pao chicken | - | yes |

Note: the keywords are the ingredient lists from tools.py, so a dish word near a trigger can be read as the allergen (for example "pasta, I don't want soy" also names wheat/gluten). That errs toward asking the student to select it.

**All checks passed.**
