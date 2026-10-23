"""Diet enforcement (vegetarian, vegan, pescatarian) by code. Offline: a fake model stands in for the LLM."""

from pathlib import Path

import pytest
from fakes import GOOD_WRITER, RICE, FakeLLM, ingredient
from streamlit.testing.v1 import AppTest

import agents
import safety
import tools
from agents import RunDeps, run_pipeline
from tools import CatalogItem, check_diet

ROOT = Path(__file__).resolve().parent.parent
REAL_RUN = agents.run_pipeline


def conflicts(names, diet):
    return [c.ingredient for c in check_diet(names, diet).conflicts]


def uncertain(names, diet):
    return [u.ingredient for u in check_diet(names, diet).uncertain]


# ---------------------------------------------------------------- the keyword check

@pytest.mark.parametrize("name", ["pork belly", "pork", "beef chuck", "bacon", "ham", "chicken thigh", "turkey", "lamb", "duck breast", "sausage",
                                  "anchovy", "fish sauce", "shrimp", "oyster sauce", "gelatin", "lard", "bonito flakes", "salmon fillet", "chicken broth"])
def test_vegetarian_flags_meat_fish_and_shellfish(name):
    assert conflicts([name], "vegetarian") == [name]


@pytest.mark.parametrize("name", ["tofu", "mushrooms", "coconut milk", "eggs", "milk", "butter", "cheddar cheese", "honey", "rice", "scallions", "soy sauce"])
def test_vegetarian_allows_plant_foods_dairy_eggs_and_honey(name):
    assert conflicts([name], "vegetarian") == []


@pytest.mark.parametrize("name", ["milk", "egg", "honey", "butter", "heavy cream", "cheddar cheese", "ghee", "egg noodles", "mayonnaise", "pork belly"])
def test_vegan_flags_dairy_eggs_honey_and_the_vegetarian_list(name):
    assert conflicts([name], "vegan") == [name]


@pytest.mark.parametrize("name", ["eggplant", "coconut milk", "coconut cream", "soy milk", "almond milk", "oyster mushroom", "peanut butter",
                                  "butternut squash", "cocoa butter", "cream of tartar", "tofu", "mushrooms", "crab apple", "beef tomato"])
def test_look_alikes_are_not_flagged_for_any_enforced_diet(name):
    for diet in ("vegetarian", "vegan", "pescatarian"):
        assert conflicts([name], diet) == [], (name, diet)


def test_pescatarian_allows_fish_and_shellfish_but_not_meat():
    assert conflicts(["salmon", "shrimp", "fish sauce", "oyster sauce", "tuna"], "pescatarian") == []
    assert conflicts(["pork belly", "chicken", "beef stock", "gelatin"], "pescatarian") == ["pork belly", "chicken", "beef stock", "gelatin"]


def test_kimchi_worcestershire_stock_and_curry_paste_are_uncertain_not_conflicts():
    check = check_diet(["kimchi", "Worcestershire sauce", "stock", "curry paste", "dashi"], "vegetarian")
    assert check.conflicts == []
    assert [u.ingredient for u in check.uncertain] == ["kimchi", "Worcestershire sauce", "stock", "curry paste", "dashi"]
    assert "fish sauce or shrimp" in check.uncertain[0].reason and "check the label" in check.uncertain[0].reason
    assert check.all_clear is False


def test_vegetable_broth_is_fine_but_plain_broth_is_uncertain():
    assert uncertain(["vegetable broth", "mushroom stock"], "vegetarian") == []
    assert uncertain(["broth", "bouillon cube"], "vegan") == ["broth", "bouillon cube"]


def test_a_vegetarian_or_vegan_label_never_clears_an_item():
    assert conflicts(["vegan oyster sauce"], "vegetarian") == []
    assert uncertain(["vegan oyster sauce"], "vegetarian") == ["vegan oyster sauce"]
    assert uncertain(["vegan butter"], "vegan") == ["vegan butter"]
    assert check_diet(["vegetarian stock"], "vegetarian").all_clear is False


def test_pescatarian_does_not_make_kimchi_uncertain_for_fish_sauce():
    assert uncertain(["kimchi", "Worcestershire sauce"], "pescatarian") == []
    assert uncertain(["stock"], "pescatarian") == ["stock"]


def test_catalog_tags_count_for_diets():
    cod = tools.find_catalog_item("Wild Atlantic Cod Fillet per lb", "Whole Foods")
    milk = tools.find_catalog_item("Organic Plain Whole Milk Yogurt 32 oz", "Whole Foods")
    assert isinstance(cod, CatalogItem) and conflicts([cod], "vegetarian") == [cod.product_name] and conflicts([cod], "pescatarian") == []
    assert conflicts([milk], "vegetarian") == [] and conflicts([milk], "vegan") == [milk.product_name]


@pytest.mark.parametrize("diet", ["halal", "kosher", "low-carb", "none", ""])
def test_other_preferences_are_not_enforced_and_never_claim_clear(diet):
    check = check_diet(["pork belly", "rice"], diet)
    assert check.enforced is False and check.conflicts == [] and check.uncertain == [] and check.all_clear is False


def test_all_clear_only_with_no_conflicts_and_nothing_uncertain():
    assert check_diet(["rice", "tofu", "scallions"], "vegetarian").all_clear is True


# ---------------------------------------------------------------- the pipeline

VEG = RunDeps(store="Walmart", servings=2, dietary_preferences=["vegetarian"])
PORK_DISH = [ingredient("white rice", 100, RICE), ingredient("pork belly", 60, None, role="protein")]
PORK_REMOVED = {"substitutions": [{"original_name": "pork belly", "status": "no_substitute", "product_name": None,
                                    "taste_texture_note": "Less rich.", "reason": "Not vegetarian.", "closest_option_or_skip": "skip it"}]}
WRITER_USES_PORK = {**GOOD_WRITER, "steps": ["Cook 200 g rice for 15 minutes.", "Brown the pork belly in a pan, then serve over the rice."]}
WRITER_OK = {**GOOD_WRITER, "steps": ["Cook 200 g rice for 15 minutes.", "Skip the pork belly and serve the rice warm."]}


def run(llm, deps=VEG, text="pork rice bowl"):
    return run_pipeline(text, deps, model=llm.model())


def check_names(result):
    return [(c.name, c.status) for c in result.safety_checks]


def test_vegetarian_with_pork_belly_triggers_one_rerun_that_removes_it():
    llm = FakeLLM(dish=PORK_DISH, substitutions=[PORK_REMOVED], writer=[WRITER_OK])
    result = run(llm)
    assert llm.calls["substitution"] == 1  # the only substitution call is the diet re-run
    prompt = llm.prompts["substitution"][0]
    assert "CONFLICTING with the student's vegetarian diet" in prompt and "pork belly" in prompt and "dietary preferences=['vegetarian']" in prompt
    assert result.diet_hard_stop is False and result.status == "complete"
    assert "pork belly" in result.verified.omitted_from_adapted and "pork belly" not in [l.name for l in result.verified.adapted_ingredients]
    assert ("Diet check", "warning") in check_names(result) and ("Diet check (after re-run)", "passed") in check_names(result)


def test_the_analyst_is_still_not_told_the_diet():
    llm = FakeLLM(dish=PORK_DISH, substitutions=[PORK_REMOVED], writer=[WRITER_OK])
    run(llm)
    assert "vegetarian" not in llm.prompts["analyst"][0]


def test_a_conflict_that_remains_after_the_rerun_becomes_a_not_vegetarian_stop():
    cod = {"substitutions": [{"original_name": "pork belly", "status": "substituted", "product_name": "Wild Atlantic Cod Fillet per lb",
                               "taste_texture_note": "Flaky.", "reason": "Closest protein.", "closest_option_or_skip": None}]}
    llm = FakeLLM(dish=PORK_DISH, substitutions=[cod], writer=[WRITER_OK])
    result = run(llm, deps=RunDeps(store="Whole Foods", servings=2, dietary_preferences=["vegetarian"]))
    assert llm.calls["substitution"] == 1  # exactly one re-run
    assert result.diet_hard_stop is True
    assert [c.ingredient for c in result.diet_stop_conflicts] == ["Wild Atlantic Cod Fillet per lb"]
    assert ("Diet check (after re-run)", "blocked") in check_names(result)
    assert "'diet_conflicts': ['Wild Atlantic Cod Fillet per lb" in llm.prompts["writer"][0]


def test_writer_steps_that_use_the_removed_ingredient_are_rejected_then_regenerated():
    llm = FakeLLM(dish=PORK_DISH, substitutions=[PORK_REMOVED], writer=[WRITER_USES_PORK, WRITER_OK])
    result = run(llm)
    assert result.writer_path == "regenerated" and llm.calls["writer"] == 2
    assert "left-out ingredient pork belly" in llm.prompts["writer"][1]
    assert not any("pork belly" in step and "skip" not in step.lower() for step in result.writer.steps)


def test_writer_that_keeps_using_the_removed_ingredient_falls_back_to_the_template():
    result = run(FakeLLM(dish=PORK_DISH, substitutions=[PORK_REMOVED], writer=[WRITER_USES_PORK]))
    assert result.writer_path == "fallback"
    assert not any("Brown the pork belly" in step for step in result.writer.steps)


def test_steps_check_allows_skip_and_without_and_ignores_the_taste_note():
    facts = safety.OutputFacts(allowed_numbers={200.0, 2.0}, confirmed_products=set(), vocabulary={"pork", "belly"}, left_out=["pork belly"])

    def found(steps, other=""):
        return safety.check_output([other, *steps], facts, steps=steps)

    assert any("left-out ingredient" in v for v in found(["Brown the pork belly."]))
    assert found(["Skip the pork belly.", "Cook it without pork belly."]) == []
    assert found(["Cook 200 g rice."], other="It tastes lighter without the richness of pork belly.") == []  # not a step


def test_kimchi_is_uncertain_not_removed():
    dish = [ingredient("white rice", 100, RICE), ingredient("kimchi", 80, None, role="flavor_base")]
    llm = FakeLLM(dish=dish)
    result = run(llm)
    assert llm.calls["substitution"] == 0 and result.diet_hard_stop is False
    assert [u.ingredient for u in result.verified.diet_check.uncertain] == ["kimchi"]
    assert ("Diet check", "warning") in check_names(result)
    assert "'diet_uncertain': ['kimchi']" in llm.prompts["writer"][0]


def test_preference_none_changes_nothing():
    llm = FakeLLM()
    result = run(llm, deps=RunDeps(store="Walmart", servings=2))
    assert result.verified.diet_check is None and not result.diet_hard_stop
    assert not any(name.startswith("Diet check") for name, _ in check_names(result))
    assert "diet" not in llm.prompts["writer"][0].replace("dietary_preferences", "")


def test_halal_is_passed_to_the_ai_and_reported_as_not_verified():
    llm = FakeLLM(dish=PORK_DISH, writer=[WRITER_USES_PORK])
    result = run(llm, deps=RunDeps(store="Walmart", servings=2, dietary_preferences=["halal"]))
    assert result.diet_hard_stop is False and llm.calls["substitution"] == 0  # nothing enforced, no re-run
    assert ("Diet check", "skipped") in check_names(result)
    assert any("not verified by code" in c.detail for c in result.safety_checks if c.name == "Diet check")


def test_allergen_path_is_unchanged_when_only_an_allergy_is_selected():
    llm = FakeLLM()
    result = run(llm, deps=RunDeps(store="Walmart", servings=2, allergies=["peanuts"]))
    assert not any(name.startswith("Diet check") for name, _ in check_names(result))


# ---------------------------------------------------------------- the page

def app_with(monkeypatch, llm):
    monkeypatch.setattr(agents, "run_pipeline", lambda text, settings, progress_callback=None, session=None: REAL_RUN(
        text, settings, progress_callback=progress_callback, session=session, model=llm.model()))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def go(at, diet, text="pork rice bowl"):
    at.selectbox[1].set_value(diet).run()  # sidebar: store, dietary preference, goal
    at.text_area(key="dish_text").set_value(text).run()
    at.button[-1].click().run()


def test_page_shows_a_green_diet_box_only_when_everything_is_clear(monkeypatch):
    at = app_with(monkeypatch, FakeLLM(dish=[ingredient("white rice", 100, RICE), ingredient("tofu", 50, None, role="protein")]))
    go(at, "vegetarian")
    assert "Diet check" in [h.value for h in at.subheader]
    assert any("No ingredient conflicts with vegetarian" in s.value for s in at.success)


def test_page_shows_a_yellow_box_for_kimchi(monkeypatch):
    at = app_with(monkeypatch, FakeLLM(dish=[ingredient("white rice", 100, RICE), ingredient("kimchi", 80, None, role="flavor_base")]))
    go(at, "vegetarian")
    assert any("kimchi: traditional kimchi often contains fish sauce or shrimp; check the label" in w.value for w in at.warning)
    assert not at.success


def test_page_shows_red_and_not_vegetarian_header_when_a_conflict_remains(monkeypatch):
    cod = {"substitutions": [{"original_name": "pork belly", "status": "substituted", "product_name": "Wild Atlantic Cod Fillet per lb",
                               "taste_texture_note": "Flaky.", "reason": "Closest protein.", "closest_option_or_skip": None}]}
    at = app_with(monkeypatch, FakeLLM(dish=PORK_DISH, substitutions=[cod], writer=[WRITER_OK]))
    at.selectbox[0].set_value("Whole Foods").run()
    go(at, "vegetarian")
    assert any("NOT vegetarian as written" in h.value for h in at.header)
    assert any("This is not vegetarian as written" in e.value for e in at.error)
    assert any("Not vegetarian" in e.value for e in at.error)


def test_page_shows_nothing_new_without_a_preference_and_an_info_note_for_halal(monkeypatch):
    at = app_with(monkeypatch, FakeLLM())
    at.text_area(key="dish_text").set_value("egg rice bowl").run()
    at.button[-1].click().run()
    assert "Diet check" not in [h.value for h in at.subheader]
    at = app_with(monkeypatch, FakeLLM())
    go(at, "halal", "egg rice bowl")
    assert any("passed to the AI as text" in i.value and "does not verify" in i.value for i in at.info)
    assert not at.success
