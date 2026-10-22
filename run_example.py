"""Run the pipeline end to end on examples. Real LLM calls: run sparingly.

Usage: python run_example.py            (full example, then the vague-input example)
       python run_example.py full       (only the full example)
       python run_example.py vague      (only the clarifying-question example)
"""

import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from agents import PipelineResult, RunDeps, run_pipeline  # noqa: E402


def print_result(result: PipelineResult) -> None:
    print("\n=== TRACE ===")
    for stage in result.trace:
        print(f"\n[{stage.stage}] input: {stage.input_summary}")
        if stage.note:
            print(f"  note: {stage.note}")
        for call in stage.tool_calls:
            print(f"  tool {call.name}({call.arguments}) -> {call.result_summary}")
        print(f"  output: {stage.output}")
        print(f"  usage: {stage.usage or 'no LLM call'}")

    if result.status == "needs_clarification":
        print("\n=== CLARIFYING QUESTION ===")
        print(result.clarifying_question)
    elif result.status in ("blocked", "stopped"):
        print(f"\n=== {result.status.upper()} ({result.block_category or result.limit_kind}) ===")
        print(result.message)
    else:
        print("\n=== FINAL ANSWER ===")
        print(result.answer_markdown)

    print("\n=== TOKENS PER STAGE ===")
    for stage, u in result.usage_by_stage.items():
        print(f"{stage:13} input={u['input_tokens']:>6} cached={u['cached_input_tokens']:>6} "
              f"output={u['output_tokens']:>6} requests={u['requests']} cost=${u['estimated_cost_usd']}")
    t = result.usage_total
    print(f"{'TOTAL':13} input={t['input_tokens']:>6} cached={t['cached_input_tokens']:>6} "
          f"output={t['output_tokens']:>6} requests={t['requests']} cost=${t['estimated_cost_usd']}")


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("full", "both"):
        print("######## EXAMPLE 1: Taiwanese beef noodle soup, Walmart, peanut allergy ########")
        settings = RunDeps(store="Walmart", servings=2, allergies=["peanuts"], dietary_preferences=[], goals=[])
        print_result(run_pipeline("Taiwanese beef noodle soup", settings))
    if which in ("vague", "both"):
        print("\n\n######## EXAMPLE 2: vague input ########")
        settings = RunDeps(store="Walmart", servings=2, allergies=["peanuts"], dietary_preferences=[], goals=[])
        print_result(run_pipeline("something from home", settings))


if __name__ == "__main__":
    main()
