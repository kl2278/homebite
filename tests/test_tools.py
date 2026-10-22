"""Tests for the data files and tools. Run: pytest"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import (  # noqa: E402
    ALLERGENS,
    CATALOG_PATH,
    NUTRITION_PATH,
    IngredientAmount,
    check_allergens,
    compute_recipe_nutrition,
    search_catalog,
    search_nutrition,
)

# Known USDA values per 100 g (copied from the USDA SR Legacy table).
RICE_RAW = 168877  # Rice, white, long-grain, regular, raw, enriched: 365 kcal, 7.13 protein, 0.66 fat, 79.95 carbs
EGG_RAW = 171287  # Egg, whole, raw, fresh: 143 kcal, 12.56 protein, 9.51 fat, 0.72 carbs


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- data files

def test_every_catalog_match_exists_in_nutrition():
    descriptions = {r["description"] for r in read_csv(NUTRITION_PATH)}
    missing = [r["product_name"] for r in read_csv(CATALOG_PATH) if r["usda_match_description"] not in descriptions]
    assert missing == []


def test_catalog_allergen_tags_are_valid():
    for row in read_csv(CATALOG_PATH):
        tags = [t for t in row["allergen_tags"].split(";") if t]
        assert set(tags) <= set(ALLERGENS), row["product_name"]


def test_nutrition_columns_and_size():
    rows = read_csv(NUTRITION_PATH)
    assert list(rows[0]) == ["fdc_id", "description", "kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "sugar_g", "sodium_mg"]
    assert 1500 <= len(rows) <= 3000


# ---------------------------------------------------------------- search_nutrition

def test_search_nutrition_finds_tofu():
    result = search_nutrition("tofu")
    assert result.found
    assert all("tofu" in m.description.lower() for m in result.matches)
    assert len(result.matches) <= 5


def test_search_nutrition_uses_usda_names_and_tolerates_typos():
    assert "pak-choi" in search_nutrition("bok choy").matches[0].description
    assert "lentil" in search_nutrition("lentills").matches[0].description.lower()


def test_search_nutrition_not_found_does_not_guess():
    result = search_nutrition("unobtainium")
    assert result.found is False
    assert result.matches == []


# ---------------------------------------------------------------- search_catalog

def test_search_catalog_normal_case():
    result = search_catalog("tofu", "Trader Joe's")
    assert result.found
    assert all(i.store == "Trader Joe's" for i in result.items)
    assert all(i.fdc_id is not None for i in result.items)
    assert all(i.verified is False for i in result.items)  # starter data is unverified


def test_search_catalog_store_name_is_forgiving():
    assert search_catalog("tofu", "trader joes").found


def test_search_catalog_excludes_allergens():
    result = search_catalog("soy sauce", "Walmart", exclude_allergens=["soy"])
    assert result.found is False
    assert result.excluded_for_allergens  # says what was removed and why nothing is left


def test_search_catalog_not_found_and_unknown_store():
    assert search_catalog("unobtainium", "Walmart").found is False
    unknown = search_catalog("rice", "Costco")
    assert unknown.found is False
    assert "Unknown store" in unknown.note


# ---------------------------------------------------------------- compute_recipe_nutrition

def test_recipe_nutrition_matches_hand_calculation():
    # 200 g rice + 100 g egg, 2 servings.
    # kcal: 365*2 + 143 = 873 -> 436.5 per serving
    # protein: 7.13*2 + 12.56 = 26.82 -> 13.41 per serving
    # fat: 0.66*2 + 9.51 = 10.83 -> 5.415 per serving (rounded to 2 places)
    # carbs: 79.95*2 + 0.72 = 160.62 -> 80.31 per serving
    result = compute_recipe_nutrition(
        [IngredientAmount(fdc_id=RICE_RAW, grams=200), IngredientAmount(fdc_id=EGG_RAW, grams=100)], servings=2
    )
    assert result.found
    assert result.total["kcal"] == pytest.approx(873)
    assert result.per_serving["kcal"] == pytest.approx(436.5)
    assert result.per_serving["protein_g"] == pytest.approx(13.41)
    assert result.per_serving["fat_g"] == pytest.approx(5.42, abs=0.01)
    assert result.per_serving["carbs_g"] == pytest.approx(80.31)
    assert result.missing_fdc_ids == []


def test_recipe_nutrition_reports_unknown_ingredient():
    result = compute_recipe_nutrition(
        [IngredientAmount(fdc_id=EGG_RAW, grams=100), IngredientAmount(fdc_id=999999999, grams=50)], servings=1
    )
    assert result.found
    assert result.missing_fdc_ids == [999999999]
    assert result.total["kcal"] == pytest.approx(143)  # unknown item adds nothing, and is reported


def test_recipe_nutrition_reports_nutrients_usda_does_not_have():
    # Pick a real food where USDA has no fiber value, instead of assuming one.
    gap = next(r for r in read_csv(NUTRITION_PATH) if r["fiber_g"] == "")
    result = compute_recipe_nutrition([IngredientAmount(fdc_id=int(gap["fdc_id"]), grams=100)], servings=1)
    assert int(gap["fdc_id"]) in result.incomplete_nutrients["fiber_g"]


def test_recipe_nutrition_all_unknown_and_bad_servings():
    assert compute_recipe_nutrition([IngredientAmount(fdc_id=1, grams=10)], servings=1).found is False
    assert compute_recipe_nutrition([IngredientAmount(fdc_id=EGG_RAW, grams=10)], servings=0).found is False


# ---------------------------------------------------------------- check_allergens

def test_allergen_conflict_peanut():
    result = check_allergens(["peanut butter", "rice"], ["peanuts"])
    assert [c.ingredient for c in result.conflicts] == ["peanut butter"]
    assert result.conflicts[0].allergen == "peanuts"
    assert "rice" in result.cleared
    assert result.all_clear is False


def test_allergen_conflict_from_catalog_tags():
    item = search_catalog("soy sauce", "Walmart").items[0]
    result = check_allergens([item], ["soy", "wheat_gluten", "dairy"])
    assert {c.allergen for c in result.conflicts} == {"soy", "wheat_gluten"}


def test_allergen_uncertain_is_never_safe():
    result = check_allergens(["curry paste", "dragon fruit"], ["peanuts"])
    assert [u.ingredient for u in result.uncertain] == ["curry paste", "dragon fruit"]
    assert result.conflicts == []
    assert result.cleared == []
    assert result.all_clear is False


def test_allergen_all_clear_only_when_everything_is_known():
    result = check_allergens(["rice", "carrot"], ["peanuts", "shellfish"])
    assert result.all_clear is True


def test_allergen_invalid_allergen_name_is_not_clear():
    result = check_allergens(["rice"], ["peenuts"])
    assert result.invalid_allergens == ["peenuts"]
    assert result.all_clear is False
