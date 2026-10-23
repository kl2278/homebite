"""An allergy stated in the text but not selected in the sidebar stops the request before any AI call. Run: pytest

Offline: the pipeline is replaced by a function that fails the test if it is ever called.
"""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import agents
import safety
import usage
from safety import ALLERGEN_LABELS, allergens_in_text

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "example_result.json"
DISH_TEXTS = [d["text"] for d in json.loads((ROOT / "data" / "measurement_dishes.json").read_text(encoding="utf-8"))]
EXAMPLE_TEXTS = ["Taiwanese beef noodle soup", "Croque monsieur, a French weekday lunch", "Indian tadka dal with rice"]

# one strong-trigger sentence per category
STATEMENTS = {
    "peanuts": "I am allergic to peanuts",
    "tree_nuts": "I have a tree nut allergy",
    "shellfish": "I can't eat shrimp",
    "fish": "I react to fish",
    "soy": "I'm allergic to soy",
    "wheat_gluten": "I have celiac disease",
    "eggs": "I am allergic to eggs",
    "dairy": "I am lactose intolerant",
    "sesame": "I have a sesame allergy",
}


def blocked_app(monkeypatch):
    """The real button path with a pipeline that fails the test if it runs."""
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise AssertionError("the pipeline must not run")

    monkeypatch.setattr(agents, "run_pipeline", fail)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run(), calls


def submit(at, text):
    at.text_area(key="dish_text").set_value(text).run()
    at.button[-1].click().run()


def events():
    path = safety.SAFETY_LOG_PATH
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ---------------------------------------------------------------- detection

def test_labels_match_the_sidebar():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert list(at.multiselect[0].options) == list(ALLERGEN_LABELS.values())


@pytest.mark.parametrize("category", list(STATEMENTS))
def test_each_category_is_detected_with_a_strong_trigger(category):
    assert allergens_in_text(f"kung pao chicken. {STATEMENTS[category]}.")[0] == [category]


@pytest.mark.parametrize("category", list(STATEMENTS))
def test_each_category_is_blocked_when_not_selected_and_passes_when_selected(category):
    text = f"I want to make a stir-fry, but {STATEMENTS[category]}."
    blocked = safety.allergy_text_screen(text, [])
    assert not blocked.allowed and blocked.category == "allergy_in_text" and blocked.caught_by == "rule"
    assert ALLERGEN_LABELS[category] in blocked.message
    assert safety.allergy_text_screen(text, [category]).allowed


def test_weak_triggers_behave_the_same_way():
    for text, category in [("kung pao without peanuts", "peanuts"), ("gluten-free ramen", "wheat_gluten"), ("no eggs please", "eggs"),
                           ("dairy free curry", "dairy"), ("I want to avoid sesame", "sesame"), ("free of shellfish", "shellfish"),
                           ("kung pao, I don't want soy", "soy")]:
        assert not safety.allergy_text_screen(text, []).allowed, text
        assert safety.allergy_text_screen(text, [category]).allowed, text


def test_several_allergens_in_one_sentence_are_all_listed():
    result = safety.allergy_text_screen("I am allergic to peanuts, eggs and dairy", ["eggs"])
    assert not result.allowed and "peanuts and dairy" in result.message and "eggs" not in result.message
    assert safety.allergy_text_screen("I am allergic to peanuts, eggs and dairy", ["peanuts", "eggs", "dairy"]).allowed


def test_mixed_case_and_curly_apostrophes():
    assert allergens_in_text("I CAN’T EAT Shrimp. PEANUT Allergy!") == (["peanuts", "shellfish"], [])


def test_exact_message_wording():
    result = safety.allergy_text_screen("I want to make kung pao chicken, but I am allergic to peanuts.", [])
    assert result.message == ("You mentioned peanuts as an allergy or something to avoid. HomeBite only checks the allergies "
                              "selected in the sidebar. Please select peanuts under Allergies, then describe your dish again.")


# ---------------------------------------------------------------- no false alarms

@pytest.mark.parametrize("text", DISH_TEXTS + EXAMPLE_TEXTS + [
    "Thai pad thai with shrimp", "Chinese tomato and egg stir-fry",
    "Mexican chicken tinga tacos with crema and queso fresco",
    "eggplant parmesan with butternut squash", "nutmeg cookies", "Thai green curry with coconut milk",
    "free range chicken soup", "kung pao chicken",
])
def test_dish_names_and_look_alikes_pass(text):
    assert allergens_in_text(text) == ([], [])
    assert safety.allergy_text_screen(text, []).allowed


def test_lookalikes_stay_unflagged_even_next_to_a_trigger():
    assert allergens_in_text("I'm allergic to nothing but I want eggplant, butternut squash, nutmeg and coconut milk")[0] == []


# ---------------------------------------------------------------- allergies the app has no check for

def test_other_allergens_warn_but_do_not_block():
    result = safety.allergy_text_screen("fruit salad, I am allergic to kiwi and mango", [])
    assert result.allowed and result.other_allergens == ["kiwi", "mango"]
    assert safety.other_allergen_warning(["kiwi", "mango"]) == (
        "You mentioned an allergy to kiwi and mango. HomeBite cannot check for it. Please check every ingredient and label yourself.")
    assert safety.allergy_text_screen("tacos with corn tortillas and celery", []).other_allergens == []  # no trigger


# ---------------------------------------------------------------- through the app (real button path)

def test_blocked_in_the_app_spends_zero_tokens_and_logs_one_event(monkeypatch):
    at, calls = blocked_app(monkeypatch)
    submit(at, "I want to make kung pao chicken, but I am allergic to peanuts.")
    assert not at.exception and not at.error and calls == []
    assert any("Please select peanuts under Allergies" in i.value for i in at.info)
    assert not any(m.label == "Calories" for m in at.metric)  # no recipe
    assert not usage.LOG_PATH.exists()  # nothing was recorded as usage
    log = events()
    assert len(log) == 1 and log[0]["category"] == "allergy_in_text" and log[0]["caught_by"] == "rule"
    assert any("allergy_in_text" in m.value for m in at.markdown)  # shown in the safety checks list


def test_selected_allergy_runs_normally(monkeypatch):
    calls = []

    def fake(text, settings, progress_callback=None, **kwargs):
        calls.append(settings.allergies)
        return agents.load_example(FIXTURE)[0]

    monkeypatch.setattr(agents, "run_pipeline", fake)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    at.multiselect[0].set_value(["peanuts"]).run()
    submit(at, "kung pao chicken, I am allergic to peanuts")
    assert calls == [["peanuts"]] and not events()
    assert not any("You mentioned" in w.value for w in at.warning)


def test_other_allergy_shows_a_yellow_warning_and_a_trace_line(monkeypatch):
    monkeypatch.setattr(agents, "run_pipeline", lambda text, settings, progress_callback=None, **kw: agents.load_example(FIXTURE)[0])
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    submit(at, "fruit salad, I am allergic to kiwi")
    line = "You mentioned an allergy to kiwi. HomeBite cannot check for it. Please check every ingredient and label yourself."
    assert any(w.value == line for w in at.warning)
    assert any("Other allergy in text" in m.value and line in m.value for m in at.markdown)


def test_screen_input_with_allergies_blocks_before_the_classifier():
    def classifier(text):
        raise AssertionError("the classifier must not run")

    result = safety.screen_input("I am allergic to sesame", classifier, allergies=[])
    assert not result.allowed and result.category == "allergy_in_text"
    assert safety.screen_input("I am allergic to sesame", lambda t: safety.GuardVerdict(category="ok", reason="t"), allergies=["sesame"]).allowed
