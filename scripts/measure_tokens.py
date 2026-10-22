"""Measure tokens and cost for 10 dishes x 2 configs (baseline, cost_saver), then write the reports.

Real LLM calls (20 runs). Results are saved after EVERY run and the script is resumable:
a dish/config pair that is already recorded is skipped.

  python scripts/measure_tokens.py --dry-run                 # fake model, no tokens
  python scripts/measure_tokens.py --only d01 --configs baseline   # the live smoke test
  python scripts/measure_tokens.py                           # the full measurement
  python scripts/measure_tokens.py --summarize-only          # rebuild the reports from saved runs, no LLM calls

Settings are passed to run_pipeline exactly as the app passes them. Safety limits stay on (per-run token cap,
tool and request limits). Only the per-session limits are bypassed, by giving every run a fresh SessionLimits.
Usage and safety logs go to logs/measurement/, so these runs do not count toward the daily cap.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import agents  # noqa: E402
import safety  # noqa: E402
import tools  # noqa: E402
import usage  # noqa: E402
from agents import BASELINE, COST_SAVER, RunDeps  # noqa: E402

DISHES_PATH = ROOT / "data" / "measurement_dishes.json"
CONFIGS = {"baseline": BASELINE, "cost_saver": COST_SAVER}
STAGES = ["guard", "intake", "analyst", "substitution", "writer"]  # a re-run of substitution is folded into "substitution"
MAX_PROBLEMS = 2  # stop if more than this many runs fail, are blocked, or hit limits
RUNS_PER_USER_PER_MONTH = 12  # the report author's assumption, used for the projections
USER_COUNTS = [1, 100, 10_000]
WRITER_VIOLATIONS = {"first_try": 0, "regenerated": 1, "fallback": 2}


# ================================================================ running

def load_dishes() -> list[dict]:
    return json.loads(DISHES_PATH.read_text(encoding="utf-8"))


def paths(dry_run: bool) -> dict[str, Path]:
    folder = ROOT / "logs" / ("measurement_dry" if dry_run else "measurement")
    out = ROOT / "logs" / "measurement_dry" if dry_run else ROOT / "logs"
    return {"folder": folder, "runs": folder / "runs.jsonl", "results": folder / "results",
            "csv": out / "token_report.csv", "summary": out / "token_summary.md", "experiment": out / "cost_experiment.md"}


def read_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stage_tokens(result) -> dict:
    """Per-stage tokens, requests and tool calls. A substitution re-run is added to the substitution stage."""
    stages = {name: {"input": 0, "cached": 0, "cache_write": 0, "output": 0, "requests": 0, "tool_calls": 0} for name in STAGES}
    for name, u in result.usage_by_stage.items():
        key = "substitution" if name == "substitution_rerun" else name
        if key not in stages:
            continue
        stages[key]["input"] += u["input_tokens"]
        stages[key]["cached"] += u["cached_input_tokens"]
        stages[key]["cache_write"] += u.get("cache_write_tokens", 0)
        stages[key]["output"] += u["output_tokens"]
        stages[key]["requests"] += u["requests"]
    for trace in result.trace:
        key = "substitution" if trace.stage == "substitution_rerun" else trace.stage
        if key in stages:
            stages[key]["tool_calls"] += len(trace.tool_calls)
    return stages


def quality(result, dish: dict) -> dict:
    """Quality fields, computed in code from the PipelineResult."""
    q: dict = {}
    verified = result.verified
    if verified is None:
        return q
    originals = verified.original_ingredients
    matched = sum(1 for line in originals if line.fdc_id is not None)
    q["nutrition_match_rate"] = round(matched / len(originals), 4) if originals else None
    q["unmatched_count"] = len(verified.unmatched_ingredients)
    q["writer_path"] = {"first_try": "original"}.get(result.writer_path, result.writer_path)
    q["hallucination_violations"] = WRITER_VIOLATIONS.get(result.writer_path)

    proposed = [s for s in (result.substitution_plan.substitutions if result.substitution_plan else [])
                if s.status == "substituted" and s.product_name]
    valid = [s for s in proposed if tools.find_catalog_item(s.product_name, dish["store"])]
    q["catalog_valid_rate"] = round(len(valid) / len(proposed), 4) if proposed else None
    q["proposed_substitutes"] = len(proposed)
    q["hard_to_find"] = sum(1 for i in result.analysis.ingredients if i.hard_to_find_abroad) if result.analysis else None
    chosen = [s for s in verified.substitutions if s.status == "substituted"]
    q["substituted"] = len(chosen)
    q["no_substitute"] = sum(1 for s in verified.substitutions if s.status == "no_substitute")
    q["all_taste_notes"] = all(s.taste_texture_note.strip() for s in chosen) if chosen else None

    expected = [w.lower() for w in dish["expected_allergen_conflicts"]]
    check = verified.allergen_check
    first_pass = next((t.output.get("allergen_conflicts", []) for t in result.trace if t.stage == "verifier" and t.output), [])
    q["expected_conflicts"] = expected
    q["first_pass_conflicts"] = first_pass
    q["detected_words"] = sorted({w for w in expected if any(w in c.lower() for c in first_pass)})
    q["conflict_detected"] = bool(q["detected_words"]) if expected else None
    q["residual_conflict"] = bool(check.conflicts) if dish["allergies"] else None
    final_names = " ".join(line.name.lower() for line in verified.adapted_ingredients)
    q["residual_expected_word"] = any(w in final_names for w in expected) if expected else None
    q["uncertain_count"] = len(check.uncertain)
    q["all_clear"] = check.all_clear if dish["allergies"] else None
    q["allergen_rerun"] = any(t.stage == "substitution_rerun" for t in result.trace)
    return q


def run_dish(dish: dict, config_name: str, dry_run: bool) -> dict:
    """One pipeline run through the same entry point the app uses; returns the record (not yet saved)."""
    deps = RunDeps(store=dish["store"], servings=dish["servings"], allergies=dish["allergies"],
                   dietary_preferences=[] if dish["diet"] == "none" else [dish["diet"]],
                   goals=[] if dish["goal"] == "none" else [dish["goal"]])
    record = {"dish_id": dish["id"], "config": config_name, "timestamp": datetime.now(timezone.utc).isoformat(), "attempts": 0}
    for attempt in (1, 2):  # a failed run is retried at most once
        record["attempts"] = attempt
        model = None
        if dry_run:
            from fakes import FakeLLM
            model = FakeLLM().model()
        start = time.time()
        try:
            result = agents.run_pipeline(dish["text"], deps, session=safety.SessionLimits(), model=model, config=CONFIGS[config_name])
        except Exception as error:
            record.update(status="error", error=f"{type(error).__name__}: {str(error)[:200]}", latency_s=round(time.time() - start, 2))
            continue
        record["latency_s"] = round(time.time() - start, 2)
        record["status"] = {"complete": "ok", "needs_clarification": "clarify", "blocked": "blocked", "stopped": "limit"}[result.status]
        record["error"] = result.message if result.status in ("blocked", "stopped") else ""
        record["stages"] = stage_tokens(result)
        record["quality"] = quality(result, dish)
        record["_result"] = result
        return record
    return record


def save_record(record: dict, p: dict[str, Path]) -> None:
    result = record.pop("_result", None)
    p["folder"].mkdir(parents=True, exist_ok=True)
    if result is not None:
        p["results"].mkdir(exist_ok=True)
        agents.save_result(result, p["results"] / f"{record['dish_id']}_{record['config']}.json")
    with p["runs"].open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ================================================================ derived numbers

def run_cost(record: dict) -> float:
    return sum(usage.estimate_cost(s["input"], s["cached"], s["output"], s.get("cache_write", 0)) for s in record["stages"].values())


def stage_cost(s: dict) -> float:
    return usage.estimate_cost(s["input"], s["cached"], s["output"], s.get("cache_write", 0))


def totals(record: dict) -> dict:
    keys = ("input", "cached", "cache_write", "output", "requests", "tool_calls")
    return {k: sum(s[k] for s in record["stages"].values()) for k in keys}


def token_fingerprint(record: dict) -> tuple:
    return tuple((n, s["input"], s["cached"], s["output"]) for n, s in sorted(record["stages"].items()))


def flag_cache_hits(runs: list[dict]) -> dict[tuple, bool]:
    """Suspected gateway cache hits: very low latency, or token usage identical to an earlier run."""
    flags = {}
    usable = [r for r in runs if r.get("stages") and r["status"] == "ok"]
    seen = []
    for r in sorted(usable, key=lambda r: r["timestamp"]):
        others = [o["latency_s"] for o in usable if o is not r]
        median = statistics.median(others) if others else None
        fast = median is not None and r["latency_s"] < 0.25 * median
        same = token_fingerprint(r) in seen
        flags[(r["dish_id"], r["config"])] = bool(fast or same)
        seen.append(token_fingerprint(r))
    return flags


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def mean(values) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


# ================================================================ reports

def write_csv(runs: list[dict], p: dict[str, Path]) -> None:
    flags = flag_cache_hits(runs)
    columns = ["dish_id", "config", "timestamp", "latency_s", "status", "attempts", "possible_gateway_cache"]
    for stage in STAGES:
        columns += [f"{stage}_{k}" for k in ("input", "cached", "cache_write", "output", "requests", "tool_calls")]
    columns += [f"total_{k}" for k in ("input", "cached", "cache_write", "output", "requests", "tool_calls")]
    quality_columns = ["nutrition_match_rate", "unmatched_count", "writer_path", "hallucination_violations", "catalog_valid_rate",
                       "proposed_substitutes", "hard_to_find", "substituted", "no_substitute", "all_taste_notes",
                       "expected_conflicts", "first_pass_conflicts", "conflict_detected", "detected_words", "residual_conflict",
                       "residual_expected_word", "uncertain_count", "all_clear", "allergen_rerun"]
    p["csv"].parent.mkdir(parents=True, exist_ok=True)
    with p["csv"].open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns + quality_columns)
        writer.writeheader()
        for r in runs:
            row = {c: r.get(c, "") for c in ("dish_id", "config", "timestamp", "latency_s", "status", "attempts")}
            row["possible_gateway_cache"] = flags.get((r["dish_id"], r["config"]), "")
            if r.get("stages"):
                for stage in STAGES:
                    for k, v in r["stages"][stage].items():
                        row[f"{stage}_{k}"] = v
                row.update({f"total_{k}": v for k, v in totals(r).items()})
                for k in quality_columns:
                    value = r["quality"].get(k, "")
                    row[k] = ";".join(value) if isinstance(value, list) else value
            writer.writerow(row)


def money(x: float) -> str:
    return f"${x:.6f}"


def summarize_baseline(runs: list[dict], p: dict[str, Path], flags: dict) -> str:
    ok = [r for r in runs if r["config"] == "baseline" and r["status"] == "ok" and r.get("stages")]
    out = ["# Token summary (baseline config)", ""]
    if not ok:
        return "\n".join(out + ["No successful baseline runs yet."])
    tot = [totals(r) for r in ok]
    costs = [run_cost(r) for r in ok]
    inputs, cached, outputs = [t["input"] for t in tot], [t["cached"] for t in tot], [t["output"] for t in tot]
    out += [f"Runs analysed: {len(ok)} baseline runs (one per dish), status ok. Costs are computed from tokens with the price constants below.", ""]
    cw = sum(t["cache_write"] for t in tot)
    out += ["## Prices used (USD per 1M tokens)", "",
            f"- Input ${usage.INPUT_PRICE_PER_M} | cached input ${usage.CACHED_INPUT_PRICE_PER_M} | cache write ${usage.CACHE_WRITE_PRICE_PER_M} | output ${usage.OUTPUT_PRICE_PER_M}",
            "- Source: course slides, \"Cached Token Cost\" slide, gpt-6-luna row." + (" (still marked as placeholder)" if usage.PRICES_ARE_PLACEHOLDER else ""),
            ("- Cache writes: the provider reported **0** cache-write tokens, so all non-cached input is priced at the normal input rate. "
             "Cache writes cost 25% more than normal input, so cost may be slightly underestimated.") if cw == 0 else
            f"- Cache writes: the provider reported {cw} cache-write tokens in total; they are priced at the cache-write rate.", ""]

    out += ["## Per run", "", "| Metric | Average | p90 |", "|---|---|---|",
            f"| Input tokens | {mean(inputs):,.0f} | {pct(inputs, .9):,.0f} |",
            f"| Cached input tokens | {mean(cached):,.0f} | {pct(cached, .9):,.0f} |",
            f"| Output tokens | {mean(outputs):,.0f} | {pct(outputs, .9):,.0f} |",
            f"| Cost | {money(mean(costs))} | {money(pct(costs, .9))} |",
            f"| Latency (s) | {mean(r['latency_s'] for r in ok):.1f} | {pct([r['latency_s'] for r in ok], .9):.1f} |", "",
            f"Cache hit ratio (cached input / input): **{sum(cached) / sum(inputs):.1%}**", ""]

    out += ["## Breakdown by stage (average per run)", "",
            "| Stage | Input | Cached | Output | Cost | Share of cost | Requests | Tool calls |", "|---|---|---|---|---|---|---|---|"]
    total_cost = sum(costs)
    for stage in STAGES:
        s_in = mean(r["stages"][stage]["input"] for r in ok)
        s_cached = mean(r["stages"][stage]["cached"] for r in ok)
        s_out = mean(r["stages"][stage]["output"] for r in ok)
        s_cost = sum(stage_cost(r["stages"][stage]) for r in ok)
        out.append(f"| {stage} | {s_in:,.0f} | {s_cached:,.0f} | {s_out:,.0f} | {money(s_cost / len(ok))} | "
                   f"{s_cost / total_cost:.1%} | {mean(r['stages'][stage]['requests'] for r in ok):.1f} | "
                   f"{mean(r['stages'][stage]['tool_calls'] for r in ok):.1f} |")
    out += ["", "The guard stage is the cheap input classifier; it is included in every total above.", ""]

    avg = mean(costs)
    out += ["## Projected monthly cost", "",
            f"**Assumption: {RUNS_PER_USER_PER_MONTH} runs per user per month (the report author's assumption, not measured).** "
            f"Average cost per run, including the guard stage: {money(avg)}.", "",
            "| Users | Runs per month | Estimated monthly cost |", "|---|---|---|"]
    for users in USER_COUNTS:
        runs_month = users * RUNS_PER_USER_PER_MONTH
        out.append(f"| {users:,} | {runs_month:,} | ${avg * runs_month:,.2f} |")

    mix = total_cost / sum(t["input"] + t["output"] for t in tot)
    cap = safety.DAILY_TOKEN_CAP
    out += ["", "## What the daily token cap implies", "",
            f"The cap counts input + output tokens: {cap:,} per UTC day, across all sessions.",
            f"- At the measured token mix, that is about **${cap * mix:.2f} per day** at most (${mix * 1_000_000:.4f} per 1M capped tokens).",
            f"- Worst case, if every capped token were an output token: ${cap / 1_000_000 * usage.OUTPUT_PRICE_PER_M:.2f} per day.", ""]

    flagged = sorted(k for k, v in flags.items() if v and k[1] == "baseline")
    out += ["## Suspected gateway cache hits", "",
            ("Flagged baseline runs (latency under 25% of the median of the other runs, or tokens identical to an earlier run): "
             + ", ".join(f"{d}/{c}" for d, c in flagged) + ". They are still included in the averages above.") if flagged
            else "No baseline run was flagged.", ""]

    out += ["## Assumptions and limits", "",
            "- Hosting, storage and bandwidth costs are not included.",
            "- Provider rate limits at scale (100 or 10,000 users) are not modeled.",
            f"- Only {len(ok)} dishes with one run each; the p90 of {len(ok)} samples is rough, and run-to-run variation of the model is not measured.",
            "- The 12 runs per user per month is an assumption.",
            "- Costs are estimates from token counts and the course price slide, not an invoice.",
            "- Blocked or failed runs are not part of these averages."]
    return "\n".join(out) + "\n"


def summarize_experiment(runs: list[dict], p: dict[str, Path], flags: dict) -> str:
    ok = {(r["dish_id"], r["config"]): r for r in runs if r["status"] == "ok" and r.get("stages")}
    dishes = load_dishes()
    paired = [d["id"] for d in dishes if (d["id"], "baseline") in ok and (d["id"], "cost_saver") in ok]
    out = ["# Cost experiment: baseline vs cost-saver", "",
           "Cost-saver = prompt order (static text first) + trimmed Analyst/Writer prompts + batched nutrition lookups. "
           f"{len(paired)} dishes have both runs (status ok); one run per dish and config.", ""]
    if not paired:
        return "\n".join(out + ["No paired runs yet."])

    def avg_for(config, f):
        return mean(f(ok[(d, config)]) for d in paired)

    def quality_rate(config, key):
        values = [ok[(d, config)]["quality"].get(key) for d in paired]
        values = [v for v in values if v is not None]
        return (sum(1 for v in values if v) / len(values)) if values else None

    expected_dishes = [d for d in paired if next(x for x in dishes if x["id"] == d)["expected_allergen_conflicts"]]

    def detection(config):
        if not expected_dishes:
            return None
        return sum(1 for d in expected_dishes if ok[(d, config)]["quality"].get("conflict_detected")) / len(expected_dishes)

    metrics = [
        ("Input tokens", lambda r: totals(r)["input"], "{:,.0f}"),
        ("Cached input tokens", lambda r: totals(r)["cached"], "{:,.0f}"),
        ("Output tokens", lambda r: totals(r)["output"], "{:,.0f}"),
        ("Cost per run", run_cost, "${:.6f}"),
        ("Requests", lambda r: totals(r)["requests"], "{:.1f}"),
        ("Tool calls", lambda r: totals(r)["tool_calls"], "{:.1f}"),
        ("Latency (s)", lambda r: r["latency_s"], "{:.1f}"),
    ]
    out += ["## Summary (averages over paired dishes)", "", "| Metric | Baseline | Cost-saver | Change |", "|---|---|---|---|"]
    for label, f, fmt in metrics:
        a, b = avg_for("baseline", f), avg_for("cost_saver", f)
        change = f"{(b - a) / a:+.1%}" if a else "n/a"
        out.append(f"| {label} | {fmt.format(a)} | {fmt.format(b)} | {change} |")

    def rate_row(label, fn):
        a, b = fn("baseline"), fn("cost_saver")
        show = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
        out.append(f"| {label} | {show(a)} | {show(b)} | |")

    out += ["| **Quality** | | | |"]
    for label, f, fmt in [("Nutrition match rate (avg)", lambda r: r["quality"].get("nutrition_match_rate"), "{:.1%}"),
                          ("Unmatched ingredients (avg)", lambda r: r["quality"].get("unmatched_count"), "{:.1f}"),
                          ("No-substitute count (avg)", lambda r: r["quality"].get("no_substitute"), "{:.1f}"),
                          ("Substituted count (avg)", lambda r: r["quality"].get("substituted"), "{:.1f}")]:
        a, b = avg_for("baseline", f), avg_for("cost_saver", f)
        out.append(f"| {label} | {fmt.format(a)} | {fmt.format(b)} | |")
    rate_row("Writer fallback rate", lambda c: mean([1.0 if ok[(d, c)]["quality"].get("writer_path") == "fallback" else 0.0 for d in paired]))
    rate_row("Writer regeneration rate", lambda c: mean([1.0 if ok[(d, c)]["quality"].get("writer_path") == "regenerated" else 0.0 for d in paired]))
    rate_row("Catalog valid rate (proposed substitutes found in catalog)", lambda c: mean(
        [ok[(d, c)]["quality"].get("catalog_valid_rate") for d in paired if ok[(d, c)]["quality"].get("catalog_valid_rate") is not None]) if any(
        ok[(d, c)]["quality"].get("catalog_valid_rate") is not None for d in paired) else None)
    rate_row(f"Allergen detection rate (conflict_detected / expected, {len(expected_dishes)} dishes)", detection)
    out.append("| Residual allergen conflicts (count) | "
               + " | ".join(str(sum(1 for d in paired if ok[(d, c)]["quality"].get("residual_conflict"))) for c in ("baseline", "cost_saver")) + " | |")
    out.append("| Expected allergen word still in final recipe (count) | "
               + " | ".join(str(sum(1 for d in paired if ok[(d, c)]["quality"].get("residual_expected_word"))) for c in ("baseline", "cost_saver")) + " | |")

    out += ["", "## Where the cost goes (average per run)", "",
            "| Config | Fresh input | Cached input | Output | Total | Output share of cost |", "|---|---|---|---|---|---|"]
    split = {}
    for config in ("baseline", "cost_saver"):
        fresh = mean(sum((s["input"] - s["cached"] - s.get("cache_write", 0)) * usage.INPUT_PRICE_PER_M / 1e6 for s in ok[(d, config)]["stages"].values()) for d in paired)
        cache = mean(sum(s["cached"] * usage.CACHED_INPUT_PRICE_PER_M / 1e6 for s in ok[(d, config)]["stages"].values()) for d in paired)
        outp = mean(sum(s["output"] * usage.OUTPUT_PRICE_PER_M / 1e6 for s in ok[(d, config)]["stages"].values()) for d in paired)
        write = mean(sum(s.get("cache_write", 0) * usage.CACHE_WRITE_PRICE_PER_M / 1e6 for s in ok[(d, config)]["stages"].values()) for d in paired)
        total = fresh + cache + outp + write
        split[config] = total
        out.append(f"| {config} | {money(fresh + write)} | {money(cache)} | {money(outp)} | {money(total)} | {outp / total:.1%} |")
    out += ["", f"Output tokens cost {usage.OUTPUT_PRICE_PER_M / usage.INPUT_PRICE_PER_M:.0f}x normal input and "
            f"{usage.OUTPUT_PRICE_PER_M / usage.CACHED_INPUT_PRICE_PER_M:.0f}x cached input, which is why they dominate even though there are fewer of them.", ""]

    out += ["## Per dish", "", "| Dish | Config | Input | Cached | Output | Cost | Requests | Latency (s) | Nutrition match | Writer path | Substituted / none | Residual conflict | Cache flag |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in paired:
        for config in ("baseline", "cost_saver"):
            r = ok[(d, config)]
            t, q = totals(r), r["quality"]
            out.append(f"| {d} | {config} | {t['input']:,} | {t['cached']:,} | {t['output']:,} | {money(run_cost(r))} | {t['requests']} | "
                       f"{r['latency_s']:.1f} | {q.get('nutrition_match_rate', 0):.0%} | {q.get('writer_path')} | "
                       f"{q.get('substituted')} / {q.get('no_substitute')} | {q.get('residual_conflict')} | "
                       f"{'yes' if flags.get((d, config)) else ''} |")

    # Verdict, generated from the numbers.
    diffs = [run_cost(ok[(d, "cost_saver")]) - run_cost(ok[(d, "baseline")]) for d in paired]
    mean_diff = mean(diffs)
    sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    se = sd / (len(diffs) ** 0.5) if len(diffs) > 1 else float("inf")
    cheaper = sum(1 for x in diffs if x < 0)
    base_cost = avg_for("baseline", run_cost)
    change = mean_diff / base_cost if base_cost else 0.0
    noisy = abs(mean_diff) < 2 * se
    out += ["", "## Verdict", ""]
    out.append(f"- **Cost:** the cost-saver changed the average cost per run by {change:+.1%} "
               f"({money(base_cost)} to {money(base_cost + mean_diff)}). It was cheaper on {cheaper} of {len(paired)} dishes. "
               + ("This difference is **within noise** for one run per dish (the mean paired difference is under 2 standard errors)."
                  if noisy else "The paired difference is larger than 2 standard errors, so it is probably real, but it is still only 10 dishes with one run each."))
    flagged_pairs = [d for d in paired if flags.get((d, "baseline")) or flags.get((d, "cost_saver"))]
    if flagged_pairs:
        out.append(f"- **Caution:** possible gateway cache hits affected {', '.join(flagged_pairs)}; their token counts may not be independent measurements.")
    quality_bits = []
    for label, key in (("fallback", "fallback"), ("regeneration", "regenerated")):
        a = sum(1 for d in paired if ok[(d, "baseline")]["quality"].get("writer_path") == key)
        b = sum(1 for d in paired if ok[(d, "cost_saver")]["quality"].get("writer_path") == key)
        quality_bits.append(f"Writer {label}: {a} (baseline) vs {b} (cost-saver)")
    match_a, match_b = avg_for("baseline", lambda r: r["quality"].get("nutrition_match_rate")), avg_for("cost_saver", lambda r: r["quality"].get("nutrition_match_rate"))
    res_a = sum(1 for d in paired if ok[(d, "baseline")]["quality"].get("residual_conflict"))
    res_b = sum(1 for d in paired if ok[(d, "cost_saver")]["quality"].get("residual_conflict"))
    det_a, det_b = detection("baseline"), detection("cost_saver")
    out.append(f"- **Quality:** nutrition match {match_a:.1%} vs {match_b:.1%}; " + "; ".join(quality_bits)
               + f"; residual allergen conflicts {res_a} vs {res_b}"
               + (f"; allergen detection {det_a:.0%} vs {det_b:.0%}" if det_a is not None else "") + ".")
    match_diffs = [ok[(d, "cost_saver")]["quality"].get("nutrition_match_rate", 0) - ok[(d, "baseline")]["quality"].get("nutrition_match_rate", 0) for d in paired]
    lower, higher = sum(1 for x in match_diffs if x < -1e-9), sum(1 for x in match_diffs if x > 1e-9)
    tied = len(match_diffs) - lower - higher
    direction = ("the same direction in most dishes, so it is unlikely to be noise alone" if max(lower, higher) >= 0.7 * max(lower + higher, 1) and lower + higher >= 5
                 else "mixed in direction, so it is within noise")
    out.append(f"- **Nutrition match per dish:** the cost-saver was lower on {lower}, higher on {higher}, equal on {tied} of {len(paired)} dishes ({direction}). "
               "Ingredients without a USDA match are left out of the nutrition totals, so a lower match rate means less complete numbers.")
    out.append("- **How to read the quality differences:** with 10 dishes, one dish is a 10-point swing, and the model is not deterministic, "
               "so small differences in these rates are within noise. A change in writer fallbacks, residual allergen conflicts or "
               "allergen detection would deserve a closer look at the individual dishes above.")
    out.append("- Nothing was tuned after seeing these numbers; the settings are the ones fixed before the run.")
    return "\n".join(out) + "\n"


def write_reports(p: dict[str, Path]) -> None:
    runs = read_runs(p["runs"])
    write_csv(runs, p)
    flags = flag_cache_hits(runs)
    p["summary"].write_text(summarize_baseline(runs, p, flags), encoding="utf-8")
    p["experiment"].write_text(summarize_experiment(runs, p, flags), encoding="utf-8")


# ================================================================ main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="use the fake model from tests/fakes.py (no tokens)")
    parser.add_argument("--only", help="run one dish id, e.g. d01")
    parser.add_argument("--configs", default="baseline,cost_saver", help="comma-separated: baseline, cost_saver")
    parser.add_argument("--summarize-only", action="store_true", help="rebuild the reports from saved runs, no LLM calls")
    parser.add_argument("--retry-errors", action="store_true", help="run pairs again whose saved status is error")
    parser.add_argument("--ignore-failures", action="store_true", help="do not stop after more than 2 problem runs")
    args = parser.parse_args()

    p = paths(args.dry_run)
    if args.summarize_only:
        write_reports(p)
        print("Reports rebuilt from", p["runs"])
        return 0

    p["folder"].mkdir(parents=True, exist_ok=True)
    usage.LOG_PATH = p["folder"] / "usage.jsonl"  # keep measurement usage out of logs/usage.jsonl and the daily cap
    safety.SAFETY_LOG_PATH = p["folder"] / "safety_events.jsonl"

    configs = [c.strip() for c in args.configs.split(",")]
    dishes = [d for d in load_dishes() if not args.only or d["id"] == args.only]
    recorded = read_runs(p["runs"])
    done = {(r["dish_id"], r["config"]): r for r in recorded if not (args.retry_errors and r["status"] == "error")}
    problems = sum(1 for r in recorded if r["status"] != "ok")

    for index, dish in enumerate(load_dishes()):
        if dish not in dishes:
            continue
        order = list(configs)
        if index % 2 == 1:  # dish 1 baseline first, dish 2 cost_saver first, and so on
            order.reverse()
        for config_name in order:
            if (dish["id"], config_name) in done:
                print(f"skip {dish['id']}/{config_name} (already recorded)")
                continue
            print(f"run  {dish['id']}/{config_name}: {dish['text']}", flush=True)
            record = run_dish(dish, config_name, args.dry_run)
            save_record(record, p)
            write_csv(read_runs(p["runs"]), p)  # the report CSV is refreshed after every run
            line = f"     status={record['status']} latency={record.get('latency_s')}s"
            if record.get("stages"):
                t = totals(record)
                line += f" tokens in={t['input']} cached={t['cached']} out={t['output']} cost=${run_cost(record):.5f}"
            print(line + (f" error={record['error']}" if record.get("error") else ""), flush=True)
            if record["status"] != "ok":
                problems += 1
                if problems > MAX_PROBLEMS and not args.ignore_failures:
                    print(f"STOPPING: more than {MAX_PROBLEMS} runs failed, were blocked, or hit limits. Look at {p['runs']} first.")
                    write_reports(p)
                    return 2
    write_reports(p)
    print("Reports written:", p["csv"], p["summary"], p["experiment"], sep="\n  ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
