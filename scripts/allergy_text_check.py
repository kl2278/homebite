"""Evidence for the allergy-in-text rule. Writes logs/allergy_text_check.md. Free: no live calls, no tokens.

BEFORE: the pipeline as it behaved when the text named an allergy that was not selected, run with the fake model
(tests/fakes.py), which answers the way the live run did (a recipe containing peanuts and peanut oil).
AFTER: the same text through the app's real button path (app.py, via Streamlit AppTest). The pipeline is replaced by a
function that fails if it is called, so a pass proves that no AI call was made.

Run: python scripts/allergy_text_check.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
os.environ.setdefault("PORTKEY_API_KEY", "fake-key-for-this-check")  # never used: the model is fake

import agents  # noqa: E402
import safety  # noqa: E402
import usage  # noqa: E402
from fakes import EGG, FakeLLM, RICE, ingredient  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

TEXT = "I want to make kung pao chicken, but I am allergic to peanuts."
REPORT = ROOT / "logs" / "allergy_text_check.md"
tmp = Path(tempfile.mkdtemp())
safety.SAFETY_LOG_PATH = tmp / "safety_events.jsonl"
usage.LOG_PATH = tmp / "usage.jsonl"


def before() -> list[str]:
    dish = [ingredient("white rice", 100, RICE), ingredient("peanuts", 30, None, role="texture"),
            ingredient("peanut oil", 16, None, role="texture"), ingredient("egg", 50, EGG, role="protein")]
    writer = {"intro": "A simple kung pao style stir-fry for two.", "steps": ["Heat the peanut oil in a pan.", "Add the peanuts and stir-fry."],
              "taste_differences": "Close to the original."}
    llm = FakeLLM(guard="medical_context", dish=dish, writer=[writer])
    result = agents.run_pipeline(TEXT, agents.RunDeps(store="Walmart", servings=2, allergies=[]), model=llm.model())
    names = [f"{i.name} {i.grams_per_serving:g} g" for i in result.verified.adapted_ingredients]
    return [f"- status: {result.status}; AI calls made: {sum(llm.calls.values())} (guard classifier, Intake, Analyst, Substitution, Writer)",
            f"- ingredients in the recipe: {', '.join(names)}",
            f"- allergen check: no conflicts reported, because no allergy was selected (conflicts: {len(result.verified.allergen_check.conflicts)})",
            f"- notices shown: blue medical banner (medical_context={result.medical_context}); lower on the page, \"You didn't select any allergies, so no allergen check was run.\""]


def after(text: str, selected: list[str] | None = None) -> tuple[list[str], dict]:
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise AssertionError("the pipeline must not run")

    usage.LOG_PATH = tmp / f"usage_after_{len(list(tmp.iterdir()))}.jsonl"  # a fresh usage log: the BEFORE run wrote to the old one
    if safety.SAFETY_LOG_PATH.exists():
        safety.SAFETY_LOG_PATH.unlink()
    saved = agents.run_pipeline
    agents.run_pipeline = fail
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        if selected:
            at.multiselect[0].set_value(selected).run()
        at.text_area(key="dish_text").set_value(text).run()
        at.button[-1].click().run()
    finally:
        agents.run_pipeline = saved
    log = [json.loads(line) for line in safety.SAFETY_LOG_PATH.read_text().splitlines()] if safety.SAFETY_LOG_PATH.exists() else []
    return [i.value for i in at.info], {"calls": len(calls), "events": log, "usage_file": usage.LOG_PATH.exists(), "exception": bool(at.exception)}


def main() -> int:
    out = ["# Allergy stated in the text, not selected in the sidebar: before and after", "",
           "Found by my own manual test before recording the demo video: with the sidebar Allergies box empty and store Walmart, "
           f"I typed `{TEXT}` and clicked Adapt. The live run returned a recipe with 30 g of peanuts and 16 g of peanut oil. "
           "This file is generated offline (no live calls, no tokens) by `scripts/allergy_text_check.py`.", "",
           "## Before: the text above, nothing selected (fake model that answers like the live run)", ""] + before() + [""]

    messages, info = after(TEXT)
    ok = info["calls"] == 0 and len(info["events"]) == 1 and not info["usage_file"] and not info["exception"]
    out += ["## After: the same text through the app's real button path", "",
            f"- AI calls made: {info['calls']} (the pipeline was replaced by a function that fails if called)",
            f"- tokens spent: 0 (usage log written: {info['usage_file']})",
            f"- safety events written: {len(info['events'])}: category `{info['events'][0]['category']}`, caught by `{info['events'][0]['caught_by']}`" if info["events"] else "- safety events written: 0",
            "- message shown (blue info box):", "", f"> {messages[-1] if messages else '(none)'}", "",
            f"Result: **{'PASS' if ok else 'FAIL'}**", ""]

    mentioned = "I want to make kung pao chicken, but I am allergic to peanuts."
    selected_screen = safety.allergy_text_screen(mentioned, ["peanuts"])
    out += ["## Same text with Peanuts selected in the sidebar", "",
            f"- blocked: {not selected_screen.allowed} (the request proceeds normally, as before the fix)", ""]

    kiwi = safety.allergy_text_screen("fruit salad, I am allergic to kiwi and mango", [])
    out += ["## An allergy outside the nine sidebar categories", "",
            f"- blocked: {not kiwi.allowed}; warning shown above the results: \"{safety.other_allergen_warning(kiwi.other_allergens)}\"", ""]

    bad = []
    out += ["## Statements that stop the request when the allergen is not selected", "", "| Text | Allergens found | Stopped |", "|---|---|---|"]
    for text in ["kung pao without peanuts", "gluten-free ramen", "I can't eat shrimp or eggs", "dairy free curry", "no sesame please",
                 "I react to fish", "I have celiac disease", "I'm lactose intolerant", "I have a tree nut allergy", "I'm allergic to soy"]:
        found, _ = safety.allergens_in_text(text)
        stopped = not safety.allergy_text_screen(text, []).allowed
        bad += [] if stopped else [text]
        out.append(f"| {text} | {', '.join(found) or '-'} | {'yes' if stopped else 'NO'} |")
    out += ["", "## False-alarm check: these must pass (nothing selected)", "", "| Text | Allergens found | Passes |", "|---|---|---|"]
    dishes = [d["text"] for d in json.loads((ROOT / "data" / "measurement_dishes.json").read_text(encoding="utf-8"))]
    passing = ["Taiwanese beef noodle soup", "Croque monsieur, a French weekday lunch", "Indian tadka dal with rice"] + dishes + [
        "Mexican chicken tinga tacos with crema and queso fresco", "eggplant parmesan with butternut squash", "nutmeg cookies",
        "Thai green curry with coconut milk", "free range chicken soup", "kung pao chicken"]
    for text in dict.fromkeys(passing):
        found, others = safety.allergens_in_text(text)
        passes = safety.allergy_text_screen(text, []).allowed and not found
        bad += [] if passes else [text]
        out.append(f"| {text} | {', '.join(found) or '-'} | {'yes' if passes else 'NO'} |")
    out += ["", "Note: the keywords are the ingredient lists from tools.py, so a dish word near a trigger can be read as the allergen "
            "(for example \"pasta, I don't want soy\" also names wheat/gluten). That errs toward asking the student to select it.", ""]
    out.append(f"**{'All checks passed.' if ok and not bad else 'FAILED: ' + '; '.join(bad)}**")
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 0 if ok and not bad else 1


if __name__ == "__main__":
    sys.exit(main())
