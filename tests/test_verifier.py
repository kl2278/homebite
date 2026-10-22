"""Offline tests for the code-only Verifier (no LLM calls). Run: pytest"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import DishAnalysis, DishIngredient, Request, RunDeps, Substitution, SubstitutionPlan, verify  # noqa: E402

RICE = 168877  # Rice, white, long-grain, regular, raw, enriched
REQUEST = Request(dish_name="test", cuisine_origin="test", servings=2, goals=[])


def ingredient(name, grams, hard, fdc_id):
    return DishIngredient(name=name, grams_per_serving=grams, role="starch", hard_to_find_abroad=hard, fdc_id=fdc_id)


def test_real_catalog_product_is_accepted_and_counted():
    deps = RunDeps(store="Walmart")
    analysis = DishAnalysis(ingredients=[ingredient("short grain rice", 100, True, None)])
    plan = SubstitutionPlan(substitutions=[Substitution(
        original_name="short grain rice", status="substituted", product_name="Great Value Long Grain White Rice 5 lb",
        taste_texture_note="less sticky", reason="closest rice")])
    verified, _ = verify(REQUEST, analysis, plan, deps, seen_ids=set())
    assert verified.substitutions[0].status == "substituted"
    assert verified.adapted_nutrition.per_serving["kcal"] == 365  # 100 g per serving of the USDA rice entry
    assert verified.original_nutrition.found is False  # original had no USDA match
    assert verified.unmatched_ingredients == ["short grain rice"]


def test_invented_product_is_downgraded_to_no_substitute():
    deps = RunDeps(store="Walmart")
    analysis = DishAnalysis(ingredients=[ingredient("doubanjiang", 8, True, None)])
    plan = SubstitutionPlan(substitutions=[Substitution(
        original_name="doubanjiang", status="substituted", product_name="Imaginary Chili Paste", taste_texture_note="", reason="made up")])
    verified, _ = verify(REQUEST, analysis, plan, deps, seen_ids=set())
    assert verified.substitutions[0].status == "no_substitute"
    assert verified.omitted_from_adapted == ["doubanjiang"]


def test_product_from_another_store_is_rejected():
    analysis = DishAnalysis(ingredients=[ingredient("tofu", 100, True, None)])
    plan = SubstitutionPlan(substitutions=[Substitution(
        original_name="tofu", status="substituted", product_name="Organic Extra Firm Tofu 14 oz", taste_texture_note="", reason="")])
    verified, _ = verify(REQUEST, analysis, plan, RunDeps(store="Walmart"), seen_ids=set())  # that product is Trader Joe's
    assert verified.substitutions[0].status == "no_substitute"


def test_fdc_id_not_seen_in_search_results_is_not_trusted():
    deps = RunDeps(store="Walmart")
    analysis = DishAnalysis(ingredients=[ingredient("rice", 100, False, RICE)])
    plan = SubstitutionPlan(substitutions=[])
    trusted, _ = verify(REQUEST, analysis, plan, deps, seen_ids={RICE})
    invented, _ = verify(REQUEST, analysis, plan, deps, seen_ids=set())
    assert trusted.original_nutrition.found is True
    assert invented.original_nutrition.found is False
    assert invented.unmatched_ingredients == ["rice"]


def test_allergen_check_runs_on_adapted_list():
    analysis = DishAnalysis(ingredients=[ingredient("peanut sauce", 20, False, None)])
    verified, _ = verify(REQUEST, analysis, SubstitutionPlan(substitutions=[]), RunDeps(store="Walmart", allergies=["peanuts"]), seen_ids=set())
    assert verified.allergen_check.conflicts and verified.allergen_check.all_clear is False


def test_saved_example_loads_and_round_trips():
    from agents import load_example, load_result, save_example, save_result

    fixture = Path(__file__).resolve().parent / "fixtures" / "example_result.json"
    result, settings, seconds = load_example(fixture)
    assert result.status == "complete" and result.verified and result.writer
    assert settings["store"] == "Walmart"  # the settings are stored in the file
    out = Path(__file__).resolve().parent / "fixtures" / "_roundtrip.json"
    try:
        save_result(result, out)
        assert load_result(out) == result
        save_example(result, settings, seconds, out)
        assert load_example(out) == (result, settings, seconds)
    finally:
        out.unlink(missing_ok=True)
