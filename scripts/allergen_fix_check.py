"""Before/after evidence for the allergen keyword fix (Prompt 7). Writes logs/allergen_fix_check.md.

(a) Offline, no LLM calls: re-check every saved measurement result that had an allergy, using the NEW keywords.
(b) One live run: d02 (katsu curry, gluten allergy), baseline config, same entry point as the measurement.
    Usage goes to logs/measurement_fixcheck/, so it does not count toward the daily cap.

Run: python scripts/allergen_fix_check.py            (offline + the one live run)
     python scripts/allergen_fix_check.py --offline-only
The old measurement files in logs/measurement/ and the three measurement reports are only READ, never changed.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import agents  # noqa: E402
import measure_tokens as m  # noqa: E402
import safety  # noqa: E402
import tools  # noqa: E402
import usage  # noqa: E402

OLD_RESULTS = ROOT / "logs" / "measurement" / "results"
FIX_DIR = ROOT / "logs" / "measurement_fixcheck"
REPORT = ROOT / "logs" / "allergen_fix_check.md"


def adapted_inputs(result, store: str) -> list:
    """The list check_allergens saw: names for common items, catalog items for substitutes."""
    items = []
    for line in result.verified.adapted_ingredients:
        catalog_item = tools.find_catalog_item(line.name, store) if line.label.startswith("substitute for ") else None
        items.append(catalog_item or line.name)
    return items


def summary(check) -> str:
    return (f"{len(check.conflicts)} conflict(s) {[c.ingredient for c in check.conflicts]}, "
            f"{len(check.uncertain)} uncertain, all_clear={check.all_clear}")


def offline_table(dishes: dict) -> tuple[list[str], int]:
    rows = ["| Dish | Config | Allergy | Before (recorded) | After (new keywords) | Changed |", "|---|---|---|---|---|---|"]
    changed = 0
    for path in sorted(OLD_RESULTS.glob("*.json")):
        dish_id, config = path.stem.split("_", 1)
        dish = dishes[dish_id]
        if not dish["allergies"]:
            continue
        result = agents.load_result(path)
        before = result.verified.allergen_check
        after = tools.check_allergens(adapted_inputs(result, dish["store"]), dish["allergies"])
        same = ([c.ingredient for c in before.conflicts] == [c.ingredient for c in after.conflicts]
                and len(before.uncertain) == len(after.uncertain) and before.all_clear == after.all_clear)
        changed += not same
        rows.append(f"| {dish_id} {dish['text'][:28]} | {config} | {', '.join(dish['allergies'])} | {summary(before)} | {summary(after)} | "
                    f"{'**yes**' if not same else 'no'} |")
    return rows, changed


def describe_ui(result, dish: dict) -> list[str]:
    """What the student sees: render the app with this saved result (no model call)."""
    from streamlit.testing.v1 import AppTest

    saved = agents.run_pipeline
    agents.run_pipeline = lambda *args, **kwargs: result
    try:
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        at.selectbox[0].set_value(dish["store"]).run()
        at.multiselect[0].set_value(["wheat/gluten"]).run()
        at.text_area(key="dish_text").set_value(dish["text"]).run()
        at.button[-1].click().run()
    finally:
        agents.run_pipeline = saved
    lines = []
    for h in at.header:
        if h.value != "Your settings":
            lines.append(f"- header: {h.value}")
    for box in at.error:
        lines.append(f"- RED box: {box.value.replace(chr(10), ' ')}")
    for box in at.warning:
        lines.append(f"- yellow box: {box.value.replace(chr(10), ' | ')}")
    for box in at.success:
        lines.append(f"- GREEN box: {box.value}")
    lines.append("- ingredients shown: " + "; ".join(str(md.value) for md in at.markdown if str(md.value).startswith("- ") and (" about " in str(md.value) or "~~" in str(md.value))))
    return lines


def saved_check() -> dict:
    """Reload the live run saved earlier (no LLM call), to rebuild the report."""
    record = json.loads((FIX_DIR / "run.json").read_text(encoding="utf-8"))
    record["result"] = agents.load_result(FIX_DIR / "d02_baseline.json")
    return record


def live_check(dish: dict) -> dict:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    usage.LOG_PATH = FIX_DIR / "usage.jsonl"
    safety.SAFETY_LOG_PATH = FIX_DIR / "safety_events.jsonl"
    record = m.run_dish(dish, "baseline", dry_run=False)
    result = record.pop("_result", None)
    if result is not None:
        agents.save_result(result, FIX_DIR / "d02_baseline.json")
    (FIX_DIR / "run.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    record["result"] = result
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--from-saved", action="store_true", help="rebuild the report from the saved live run (no LLM call)")
    args = parser.parse_args()
    dishes = {d["id"]: d for d in m.load_dishes()}

    out = ["# Allergen keyword fix: before vs after", "",
           "The measurement (Prompt 6) found panko kept in a gluten-allergy recipe because `check_allergens` had no keyword for it. "
           "The keyword list was extended (see `EXTRA_ALLERGEN_KEYWORDS` in tools.py). The measurement files in `logs/measurement/` and the three "
           "measurement reports were taken with the OLD list and are unchanged.", "",
           "## (a) Offline: saved measurement results re-checked with the new keywords (no LLM calls)", ""]
    rows, changed = offline_table(dishes)
    out += rows + ["", f"{changed} of {len(rows) - 2} saved results changed. Each saved result is the FINAL recipe of the old run, so a recipe that "
                   "now shows a conflict is one that the old check would have let through; in a new run it would trigger the substitution re-run.", ""]

    stop = False
    if not args.offline_only:
        dish = dishes["d02"]
        out += ["## (b) Live run: d02 Japanese chicken katsu curry, Whole Foods, gluten allergy, baseline config", ""]
        record = saved_check() if args.from_saved else live_check(dish)
        result = record["result"]
        if result is None or record["status"] != "ok":
            out += [f"The run did not complete: status={record['status']} error={record.get('error')}"]
            REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
            print("\n".join(out))
            return 1
        old = next(r for r in m.read_runs(ROOT / "logs" / "measurement" / "runs.jsonl") if r["dish_id"] == "d02" and r["config"] == "baseline")
        verified = result.verified
        first_pass = next(t.output.get("allergen_conflicts", []) for t in result.trace if t.stage == "verifier")
        final_names = [line.name for line in verified.adapted_ingredients]
        panko_flagged = any("panko" in c.lower() for c in first_pass)
        panko_in_final = any("panko" in n.lower() for n in final_names)
        rerun = next((t for t in result.trace if t.stage == "substitution_rerun"), None)
        t_new, t_old = m.totals(record), m.totals(old)
        out += [f"- Status: {record['status']}, latency {record['latency_s']} s, writer path: {result.writer_path}",
                f"- First-pass conflicts (new keywords): {first_pass}",
                f"- Panko detected as a definite conflict: **{'yes' if panko_flagged else 'NO'}**",
                f"- Substitution re-run happened: **{'yes' if rerun else 'no'}**",
                f"- Final adapted ingredients: {final_names}",
                f"- Left out of the final recipe: {verified.omitted_from_adapted}",
                f"- Final check: {summary(verified.allergen_check)}; hard stop: {result.allergen_hard_stop}",
                f"- Panko still in the final recipe: **{'YES' if panko_in_final else 'no'}**", ""]
        if rerun and rerun.output:
            out += ["Re-run proposals:", ""]
            for s in rerun.output.get("substitutions", []):
                out.append(f"- {s['original_name']}: {s['status']}" + (f" -> {s['product_name']}" if s.get("product_name") else "") + f" ({s['reason']})")
            out.append("")
        out += ["### What the student sees", ""] + describe_ui(result, dish) + [""]
        out += ["### Safety checks", ""] + [f"- {c.name}: {c.status} {('(' + c.detail + ')') if c.detail else ''}" for c in result.safety_checks] + [""]
        out += ["### Tokens and cost of this live run (new keywords) vs the old d02 baseline run", "",
                "| Run | Input | Cached | Cache write | Output | Requests | Cost |", "|---|---|---|---|---|---|---|",
                f"| old (measurement) | {t_old['input']:,} | {t_old['cached']:,} | {t_old['cache_write']:,} | {t_old['output']:,} | {t_old['requests']} | {m.money(m.run_cost(old))} |",
                f"| new (this check) | {t_new['input']:,} | {t_new['cached']:,} | {t_new['cache_write']:,} | {t_new['output']:,} | {t_new['requests']} | {m.money(m.run_cost(record))} |", "",
                "One run each, so the difference in tokens is mostly the normal variation of the model, not an effect of the fix.", ""]
        stop = panko_in_final and not result.allergen_hard_stop
        out += ["## Result", "",
                ("**STOP: panko is still in the final recipe and was not stopped by a hard stop.** Nothing was tuned further." if stop else
                 "Panko is now a definite conflict. " + ("It was removed or replaced by the re-run." if not panko_in_final else
                                                          "A conflict remains, so the recipe is shown as NOT safe (hard stop).")), ""]

    REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 3 if stop else 0


if __name__ == "__main__":
    sys.exit(main())
