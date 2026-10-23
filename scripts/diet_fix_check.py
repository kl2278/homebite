"""Before/after evidence for enforcing vegetarian, vegan and pescatarian by code. Writes logs/diet_fix_check.md.

(a) Offline, no LLM calls: the diet check on saved measurement results and the saved example.
(b) ONE live run through the app's own code path: Walmart, vegetarian, goal lower sodium, 2 servings, "Korean kimchi jjigae".
    Usage goes to logs/measurement_diet/, so it does not count toward the daily cap.

Run: python scripts/diet_fix_check.py              (offline + the one live run)
     python scripts/diet_fix_check.py --offline-only
     python scripts/diet_fix_check.py --from-saved   (rebuild the report from the saved live run, no LLM call)
Existing measurement files are only read, never changed.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import agents  # noqa: E402
import allergen_fix_check as afc  # noqa: E402  (reuses adapted_inputs)
import measure_tokens as m  # noqa: E402
import safety  # noqa: E402
import tools  # noqa: E402
import usage  # noqa: E402

RESULTS = ROOT / "logs" / "measurement" / "results"
LIVE_DIR = ROOT / "logs" / "measurement_diet"
REPORT = ROOT / "logs" / "diet_fix_check.md"
LIVE = {"store": "Walmart", "diet": "vegetarian", "goal": "lower sodium", "servings": 2, "text": "Korean kimchi jjigae"}


def offline(dishes: dict) -> list[str]:
    out = ["## (a) Offline: the diet check on saved results (no LLM calls)", ""]
    saved = sorted(RESULTS.glob("*.json"))
    no_diet = [p for p in saved if dishes[p.stem.split("_")[0]]["diet"] == "none"]
    unchanged = 0
    for path in no_diet:
        result = agents.load_result(path)
        # With no preference nothing new is computed: the saved results have no diet check, and an empty preference is a no-op.
        no_op = result.verified.diet_check is None and tools.check_diet(afc.adapted_inputs(result, dishes[path.stem.split("_")[0]]["store"]), "").enforced is False
        unchanged += no_op
    example, settings, _ = agents.load_example(ROOT / "tests" / "fixtures" / "example_result.json")
    out += [f"- Dishes without a dietary preference: {unchanged} of {len(no_diet)} saved measurement results are unaffected (no diet check is computed; "
            f"the saved example has none either: diet_check is {example.verified.diet_check}).", ""]

    out += ["### False-alarm check: the vegetarian ratatouille runs (d08)", "",
            "| Run | Adapted ingredients | Definite conflicts | Uncertain (check the label) |", "|---|---|---|---|"]
    for path in saved:
        dish_id, config = path.stem.split("_", 1)
        if dishes[dish_id]["diet"] != "vegetarian":
            continue
        result = agents.load_result(path)
        items = afc.adapted_inputs(result, dishes[dish_id]["store"])
        check = tools.check_diet(items, "vegetarian")
        names = ", ".join(i if isinstance(i, str) else i.product_name for i in items)
        out.append(f"| {dish_id} {config} | {names} | {[c.ingredient for c in check.conflicts] or 'none'} | "
                   f"{[f'{u.ingredient}: {u.reason}' for u in check.uncertain] or 'none'} |")
    out += ["", "### Every saved dish checked as if it were vegetarian (not real runs; shows what the keyword list catches)", "",
            "| Run | Definite conflicts | Uncertain |", "|---|---|---|"]
    for path in saved:
        dish_id, config = path.stem.split("_", 1)
        if config != "baseline":
            continue
        result = agents.load_result(path)
        check = tools.check_diet(afc.adapted_inputs(result, dishes[dish_id]["store"]), "vegetarian")
        out.append(f"| {dish_id} {dishes[dish_id]['text'][:34]} | {[c.ingredient for c in check.conflicts] or 'none'} | {[u.ingredient for u in check.uncertain] or 'none'} |")
    return out + [""]


def run_live() -> dict:
    from streamlit.testing.v1 import AppTest

    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    usage.LOG_PATH = LIVE_DIR / "usage.jsonl"
    safety.SAFETY_LOG_PATH = LIVE_DIR / "safety_events.jsonl"
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300).run()
    at.selectbox[0].set_value(LIVE["store"]).run()
    at.selectbox[1].set_value(LIVE["diet"]).run()
    at.selectbox[2].set_value(LIVE["goal"]).run()
    at.text_area(key="dish_text").set_value(LIVE["text"]).run()
    start = time.time()
    at.button[-1].click().run()
    wall = round(time.time() - start, 1)
    result = at.session_state["result"]
    agents.save_result(result, LIVE_DIR / "result.json")
    page = describe(at)
    record = {"wall_seconds": wall, "app_seconds": at.session_state["elapsed"], "page": page}
    (LIVE_DIR / "run.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def describe(at) -> list[str]:
    lines = [f"- header: {h.value}" for h in at.header if h.value != "Your settings"]
    lines += [f"- {k}: {v}" for k, v in (("metrics", [(x.label, x.value) for x in at.metric][:5]),)]
    for box in at.error:
        lines.append(f"- RED box: {box.value.replace(chr(10), ' | ')}")
    for box in at.warning:
        lines.append(f"- yellow box: {box.value.replace(chr(10), ' | ')}")
    for box in at.success:
        lines.append(f"- GREEN box: {box.value}")
    lines.append("- subheaders: " + ", ".join(s.value for s in at.subheader))
    items = [str(md.value) for md in at.markdown if str(md.value).startswith("- ") and (" about " in str(md.value) or "~~" in str(md.value))]
    lines.append("- ingredients shown: " + "; ".join(items))
    steps = [str(md.value) for md in at.markdown if re.match(r"^\d+\. ", str(md.value))]
    lines.append("- steps shown: " + " ".join(steps))
    return lines


import re  # noqa: E402


def live_section(record: dict) -> list[str]:
    result = agents.load_result(LIVE_DIR / "result.json")
    verified = result.verified
    first = next((t for t in result.trace if t.stage == "verifier"), None)
    rerun = next((t for t in result.trace if t.stage == "substitution_rerun"), None)
    steps = " ".join(result.writer.steps) if result.writer else ""
    u = result.usage_total
    cost = usage.estimate_cost(u["input_tokens"], u["cached_input_tokens"], u["output_tokens"], u.get("cache_write_tokens", 0))
    stages = {k: (v["input_tokens"], v["cached_input_tokens"], v["output_tokens"]) for k, v in result.usage_by_stage.items()}
    pork_in_final = any("pork" in line.name.lower() for line in verified.adapted_ingredients)
    out = [f"## (b) Live run: {LIVE['text']}, {LIVE['store']}, {LIVE['diet']}, goal {LIVE['goal']}, {LIVE['servings']} servings", "",
           f"- Status: {result.status}; writer path: {result.writer_path}; wall time {record['wall_seconds']} s (the app showed {record['app_seconds']} s)",
           f"- Tokens: {u['input_tokens']:,} input ({u['cached_input_tokens']:,} cached, {u.get('cache_write_tokens', 0):,} cache-write), {u['output_tokens']:,} output, {u['requests']} requests; cost {m.money(cost)}",
           f"- Tokens by stage (input, cached, output): {stages}",
           "- Diet check entries in the safety checks: " + "; ".join(f"{c.name}: {c.status} ({c.detail})" for c in result.safety_checks if c.name.startswith("Diet")),
           f"- Substitution re-run happened: {'yes' if rerun else 'no'}",
           f"- Pork belly in the final adapted ingredient list: {'YES' if pork_in_final else 'no'}; left out: {verified.omitted_from_adapted}",
           f"- 'pork' appears in the cooking steps: {'YES' if 'pork' in steps.lower() else 'no'}",
           f"- Diet hard stop: {result.diet_hard_stop}; uncertain items: {[(x.ingredient, x.reason) for x in (verified.diet_check.uncertain if verified.diet_check else [])]}", "",
           "### What the student sees", ""] + record["page"] + [""]
    if rerun and rerun.output:
        out += ["Re-run proposals:", ""] + [f"- {s['original_name']}: {s['status']} ({s['reason']})" for s in rerun.output.get("substitutions", [])] + [""]
    out += ["### Earlier result for the same settings (reported from the head-to-head test, not in the repo)", "",
            "Pork belly (120 g) stayed in the recipe as a common item, the first step browned it, and only the Writer's intro said the version is not vegetarian.", ""]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--from-saved", action="store_true")
    args = parser.parse_args()
    dishes = {d["id"]: d for d in m.load_dishes()}
    out = ["# Diet enforcement: before vs after", "",
           "A head-to-head test with a general chatbot showed that a vegetarian preference only reached the AI as text: pork belly stayed in the recipe. "
           "Vegetarian, vegan and pescatarian are now checked by code (keyword list), trigger one substitution re-run, and are shown as NOT <diet> if a conflict remains. "
           "Any other preference (halal, kosher) is still only passed to the AI and is not verified. The Goal selector is not verified either.", ""]
    out += offline(dishes)
    if not args.offline_only:
        record = json.loads((LIVE_DIR / "run.json").read_text()) if args.from_saved else run_live()
        out += live_section(record)
    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
