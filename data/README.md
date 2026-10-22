# Data notes

## nutrition.csv

Per 100 g nutrition values for 3,000 common foods, built by `scripts/build_nutrition.py`
from the USDA FoodData Central **SR Legacy** release (public domain). Columns:
`fdc_id, description, kcal, protein_g, fat_g, carbs_g, fiber_g, sugar_g, sodium_mg`.

- Values are copied from USDA. Nothing is estimated or invented.
- A blank cell means USDA did not report that nutrient for that food (it is not zero).
- Brand-name items, baby foods, fast food, restaurant food and packaged meals are left out.

## grocery_catalog.csv

**This is a starter set for demo purposes only.**

- It has 163 realistic-looking items across Walmart, Trader Joe's, Whole Foods, Aldi and
  an "Asian grocery" store.
- **Prices are illustrative and not current.** Real store prices change and vary by location.
- Product names, availability and allergen tags have **not** been checked against real
  store listings. Every row starts with `verified=false`.
- The maintainer will check entries against real store listings and set `verified=true`
  only for items they confirm.
- `usda_match_description` must exactly match a `description` in `nutrition.csv`
  (a test enforces this).
- `allergen_tags` uses semicolons and only these values: `peanuts, tree_nuts, shellfish,
  fish, soy, wheat_gluten, eggs, dairy, sesame`. Empty means no tracked allergen.
  Allergen tags are a convenience, not a safety guarantee: always read the real label.
