"""HomeBite: Streamlit UI. Run with: streamlit run app.py

The page only renders a PipelineResult. All AI calls happen inside run_pipeline.
"""

import logging
import os
import time
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import altair as alt
import pandas as pd
import streamlit as st

import usage
from agents import COMMON_LABEL, NUTRIENT_LABELS, PipelineResult, RunDeps, load_example, run_pipeline
from llm import api_key_is_set
from safety import SessionLimits

FIXTURE_PATH = Path(__file__).resolve().parent / "tests" / "fixtures" / "example_result.json"
# The saved example file holds the result AND the settings it was made with.

STORES = ["Walmart", "Trader Joe's", "Whole Foods", "Aldi", "Asian grocery"]
ALLERGY_OPTIONS = {
    "peanuts": "peanuts", "tree nuts": "tree_nuts", "shellfish": "shellfish", "fish": "fish", "soy": "soy",
    "wheat/gluten": "wheat_gluten", "eggs": "eggs", "dairy": "dairy", "sesame": "sesame",
}
DIET_OPTIONS = ["none", "vegetarian", "vegan", "halal", "kosher", "pescatarian"]
GOAL_OPTIONS = ["none", "higher protein", "lower sodium", "lower calorie"]
EXAMPLES = {
    "Taiwanese beef noodle soup": "Taiwanese beef noodle soup",
    "French weekday lunch": "Croque monsieur, a French weekday lunch",
    "Indian dal": "Indian tadka dal with rice",
}
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "requests", "estimated_cost_usd")

st.set_page_config(page_title="HomeBite", page_icon="🍜", layout="wide")

ss = st.session_state
ss.setdefault("result", None)  # the PipelineResult of the last live run
ss.setdefault("inputs", None)  # the settings that result was made with
ss.setdefault("clarify", None)  # {"text": ..., "question": ...} while waiting for an answer
ss.setdefault("error", None)
ss.setdefault("elapsed", None)  # seconds the last live run took
ss.setdefault("limits", SessionLimits())  # rate limit and token counters for this browser session
ss.setdefault("session_usage", {k: 0 for k in USAGE_KEYS})
ss.setdefault("dish_text", "")


# ================================================================ running the pipeline

MISSING_KEY_MESSAGE = (
    "HomeBite can't reach the AI service because PORTKEY_API_KEY was not found. Put a .env file containing "
    "PORTKEY_API_KEY=... in the repo folder (or in the folder one level above it), then reload this page."
)


def friendly_error(error: Exception) -> str:
    if "PORTKEY_API_KEY" in str(error):
        return MISSING_KEY_MESSAGE
    return "Something went wrong while contacting the AI service. Please try again in a moment."


def run_live(text: str, inputs: dict, diet: list[str], goals: list[str]) -> None:
    """Run the pipeline once (paid LLM calls) and keep everything in session_state."""
    ss.error, ss.clarify = None, None
    status = st.status("Starting...", expanded=True)
    status.caption("A full run usually takes about 30 seconds.")
    started = time.time()

    def on_progress(label: str) -> None:
        status.update(label=f"{label}...")
        status.write(label)

    try:
        if not api_key_is_set():
            raise RuntimeError("PORTKEY_API_KEY is not set")
        # Settings travel in RunDeps (trusted); the student's text is passed on its own.
        deps = RunDeps(store=inputs["store"], servings=inputs["servings"], allergies=inputs["allergies"],
                       dietary_preferences=diet, goals=goals)
        result = run_pipeline(text, deps, progress_callback=on_progress, session=ss.limits)
    except Exception as error:  # friendly message for the user, full details only in the server log
        logging.getLogger("homebite").exception("Pipeline failed")
        status.update(label="Something went wrong", state="error")
        ss.error = friendly_error(error)
        st.rerun()
        return

    ss.result, ss.inputs, ss.elapsed = result, inputs, round(time.time() - started, 1)
    for key in USAGE_KEYS:
        ss.session_usage[key] += result.usage_total.get(key, 0)
    if result.status == "needs_clarification":
        ss.clarify = {"text": text, "question": result.clarifying_question, "inputs": inputs, "diet": diet, "goals": goals}
    st.rerun()


# ================================================================ sidebar

with st.sidebar:
    st.header("Your settings")
    store = st.selectbox("Where do you shop?", STORES)
    allergy_labels = st.multiselect("Allergies", list(ALLERGY_OPTIONS))
    diet = st.selectbox("Dietary preference", DIET_OPTIONS)
    servings = st.slider("Servings", 1, 8, 2)
    goal = st.selectbox("Goal", GOAL_OPTIONS)
    with st.expander("Developer tools", expanded=False):
        use_fixture = st.toggle("Use saved example (no live AI call)", key="use_fixture")

inputs_now = {"store": store, "allergies": [ALLERGY_OPTIONS[a] for a in allergy_labels], "servings": servings}
diet_now = [] if diet == "none" else [diet]
goals_now = [] if goal == "none" else [goal]


# ================================================================ header and input

st.title("🍜 HomeBite")
st.write(
    "Adapt a dish from home using ingredients you can actually buy near you, "
    "with nutrition numbers computed from USDA data."
)

if use_fixture:
    st.warning("Showing a saved example, no live AI call was made.")
elif not api_key_is_set():
    st.warning(MISSING_KEY_MESSAGE)  # appears only when the key is missing


def pick_example(text: str) -> None:
    ss.dish_text = text


st.text_area("Tell me about a dish from home", key="dish_text", height=90,
             placeholder="For example: Taiwanese beef noodle soup")
st.caption("Or try an example:")
example_columns = st.columns(len(EXAMPLES))
for column, (label, text) in zip(example_columns, EXAMPLES.items()):
    column.button(label, on_click=pick_example, args=(text,), width="stretch")

if st.button("Adapt my dish", type="primary"):
    if use_fixture:
        st.info("Saved-example mode is on, so nothing was sent to the AI. Turn it off in Developer tools to run live.")
    elif not ss.dish_text.strip():
        st.warning("Please describe a dish first, or pick one of the examples.")
    else:
        run_live(ss.dish_text.strip(), inputs_now, diet_now, goals_now)


# ================================================================ errors and clarifying question

if ss.error and not use_fixture:
    st.error(ss.error)
    if st.button("Try again"):
        ss.error = None
        st.rerun()

if ss.clarify and not use_fixture:
    pending = ss.clarify
    st.info(pending["question"])
    with st.form("clarify_form"):
        answer = st.text_input("Your answer")
        submitted = st.form_submit_button("Continue")
    if submitted and answer.strip():
        combined = f"{pending['text']}\nYou asked: {pending['question']}\nMy answer: {answer.strip()}"
        run_live(combined, pending["inputs"], pending["diet"], pending["goals"])


# ================================================================ results (render only, no model calls)

def money(value: float) -> str:
    return f"${value:.2f}"


def render_ingredients(result: PipelineResult, inputs: dict) -> None:
    request, verified = result.request, result.verified
    conflicts = {c.ingredient: c.allergen.replace("_", " ") for c in result.hard_stop_conflicts}
    st.subheader("Ingredients")
    st.caption(f"For {request.servings} servings")
    for line in verified.adapted_ingredients:
        grams = round(line.grams_per_serving * request.servings, 1)
        if line.name in conflicts:
            st.markdown(f"- :red[**{line.name}: about {grams:g} g (contains {conflicts[line.name]})**]")
        else:
            st.markdown(f"- {line.name}: about {grams:g} g")
    for name in verified.omitted_from_adapted:
        st.markdown(f"- ~~{name}~~ (left out, no suitable substitute)")


def render_substitutions(result: PipelineResult, inputs: dict) -> None:
    verified = result.verified
    rows = []
    for s in verified.substitutions:
        substituted = s.status == "substituted"
        rows.append({
            "Original": s.original_name,
            "Use instead": s.product_name if substituted else "(left out)" + (f": {s.closest_option_or_skip}" if s.closest_option_or_skip else ""),
            "Store": inputs["store"] if substituted else "",
            "Price": money(s.price_usd) if substituted else "",
            "Taste / texture": s.taste_texture_note,
            "Status": s.status,
        })
    st.subheader("Substitutions")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Prices are starter catalog prices, not live.")
    else:
        st.caption("Nothing needed a substitute.")
    common = [line.name for line in verified.adapted_ingredients if line.label == COMMON_LABEL]
    with st.expander(f"Common items kept as-is ({len(common)})"):
        st.caption("Common items, not checked against the catalog.")
        st.markdown("\n".join(f"- {name}" for name in common) or "None")


def render_allergens(result: PipelineResult, inputs: dict) -> None:
    check = result.verified.allergen_check
    allergies = [a.replace("_", " ") for a in inputs["allergies"]]
    st.subheader("Allergen check")
    if not allergies:
        st.info("You didn't select any allergies, so no allergen check was run.")
        return
    if check.conflicts:
        st.error("Allergen conflict:\n" + "\n".join(f"- {c.ingredient}: {c.allergen.replace('_', ' ')} ({c.reason})" for c in check.conflicts))
    if check.uncertain:
        st.warning(
            f"Couldn't confirm these are free of {', '.join(allergies)}. Check the label.\n"
            + "\n".join(f"- {u.ingredient}" for u in check.uncertain)
        )
    if check.all_clear:
        st.success(f"No {', '.join(allergies)} found in any ingredient.")
    st.caption("Based on catalog tags and a keyword list, not a guarantee.")


def render_nutrition(result: PipelineResult) -> None:
    verified = result.verified
    comparison = verified.comparison
    st.subheader("Nutrition per serving")
    original_col, adapted_col = st.columns(2)
    kcal, sodium = comparison["kcal"], comparison["sodium_mg"]
    original_col.markdown("**Original dish**")
    original_col.metric("Calories", f"{kcal['original']:g} kcal")
    original_col.metric("Sodium", f"{sodium['original']:g} mg")
    adapted_col.markdown("**Adapted for your store**")
    adapted_col.metric("Calories", f"{kcal['adapted']:g} kcal", delta=f"{kcal['change']:+g} kcal", delta_color="off")
    adapted_col.metric("Sodium", f"{sodium['adapted']:g} mg", delta=f"{sodium['change']:+g} mg", delta_color="inverse")

    grams = ["protein_g", "fat_g", "carbs_g", "fiber_g", "sugar_g"]
    labels = [NUTRIENT_LABELS[k].replace(" (g)", "") for k in grams]
    chart_data = pd.DataFrame(
        [{"Nutrient": label, "Version": version.capitalize(), "Grams": comparison[k][version]}
         for k, label in zip(grams, labels) for version in ("original", "adapted")]
    )
    bars = alt.Chart(chart_data).encode(
        x=alt.X("Nutrient:N", sort=labels, title=None, axis=alt.Axis(labelAngle=0)),
        xOffset="Version:N",
        y=alt.Y("Grams:Q", title="Grams"),
        color=alt.Color("Version:N", scale=alt.Scale(domain=["Original", "Adapted"])),
    )
    chart = bars.mark_bar() + bars.mark_text(dy=-6, fontSize=11).encode(text=alt.Text("Grams:Q", format=".1f"))
    st.altair_chart(chart.properties(title="Per serving, original vs adapted", height=300), width="stretch")

    missing = verified.unmatched_ingredients
    if missing:
        st.caption(f"Totals exclude: {', '.join(missing)} (no USDA entry); actual values are likely a bit higher.")
    for label, nutrition in (("original", verified.original_nutrition), ("adapted", verified.adapted_nutrition)):
        if nutrition.incomplete_nutrients:
            st.caption(f"USDA has no value for {', '.join(nutrition.incomplete_nutrients)} in some ingredients of the {label} version.")
    st.caption("Substitutes are assumed to be used 1:1 by weight.")


SAFETY_ICONS = {"passed": "✅", "warning": "⚠️", "blocked": "⛔", "skipped": "➖"}


def render_trace(result: PipelineResult) -> None:
    with st.expander("How this was made"):
        st.markdown("**Safety checks**")
        if result.safety_checks:
            for check in result.safety_checks:
                st.markdown(f"- {SAFETY_ICONS[check.status]} **{check.name}**: {check.status}" + (f" ({check.detail})" if check.detail else ""))
            if result.writer_path:
                st.caption(f"Writer text path: {result.writer_path}")
        else:
            st.caption("This saved example was recorded before the safety checks were added.")
        st.divider()
        for stage in result.trace:
            st.markdown(f"**{stage.stage.capitalize()}**" + (" (code only, no AI)" if stage.stage == "verifier" else ""))
            st.caption(f"Input: {stage.input_summary}")
            if stage.note:
                st.caption(stage.note)
            for call in stage.tool_calls:
                st.text(f"tool: {call.name}({call.arguments})\n  -> {call.result_summary}")
            if stage.output is not None:
                st.json(stage.output, expanded=False)
            if stage.usage:
                u = stage.usage
                st.caption(f"Tokens: {u['input_tokens']} in ({u['cached_input_tokens']} cached), {u['output_tokens']} out, "
                           f"{u['requests']} request(s)")
            st.divider()


def render_usage(result: PipelineResult, saved_example: bool) -> None:
    st.subheader("Usage")
    row = lambda label, u: {  # noqa: E731
        "": label, "Input tokens": u["input_tokens"], "Cached input": u["cached_input_tokens"],
        "Output tokens": u["output_tokens"], "Requests": u["requests"], "Est. cost": f"${u['estimated_cost_usd']:.4f}",
    }
    rows = [row("Saved example run" if saved_example else "This run", result.usage_total), row("Session total", ss.session_usage)]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if usage.PRICES_ARE_PLACEHOLDER:
        st.caption("Estimated cost uses placeholder prices.")
    else:
        st.caption("Estimated cost uses gpt-6-luna prices from the course pricing slide.")


def allergen_status(result: PipelineResult, inputs: dict) -> str:
    check = result.verified.allergen_check
    if not inputs["allergies"]:
        return "No allergies selected"
    if result.allergen_hard_stop or check.conflicts:
        return "Conflict"
    return "Clear" if check.all_clear else "Uncertain"


def render_summary(result: PipelineResult, inputs: dict, run_seconds: float | None) -> None:
    subs = result.verified.substitutions
    items = [
        ("Substitutes found", str(sum(1 for s in subs if s.status == "substituted"))),
        ("Items left out", str(sum(1 for s in subs if s.status == "no_substitute"))),
        ("Allergen status", allergen_status(result, inputs)),
    ]
    if run_seconds is not None:
        items.append(("Run time", f"{run_seconds:.0f} s"))
    cost = result.usage_total.get("estimated_cost_usd")
    if cost is not None:
        items.append(("Est. cost", f"${cost:.4f}"))
    for column, (label, value) in zip(st.columns(len(items)), items):
        column.metric(label, value)


def render_result(result: PipelineResult, inputs: dict, saved_example: bool, run_seconds: float | None = None) -> None:
    request, writer = result.request, result.writer
    st.divider()
    if result.allergen_hard_stop:
        allergens = ", ".join(sorted({c.allergen.replace("_", " ") for c in result.hard_stop_conflicts}))
        st.header(f"{request.dish_name}: NOT safe for {allergens} as written")
        st.error(
            "Do not cook this as written. It contains: "
            + "; ".join(f"**{c.ingredient}** ({c.allergen.replace('_', ' ')})" for c in result.hard_stop_conflicts)
            + ". Leave these ingredients out, or choose a different recipe."
        )
    else:
        st.header(f"{request.dish_name} at {inputs['store']}")
    if result.writer_path == "fallback":
        st.info("This is a simplified version: the full recipe text didn't pass our safety checks, "
                "so only the verified ingredients and substitutions are shown.")
    render_summary(result, inputs, run_seconds)
    st.write(writer.intro)

    left, right = st.columns([1, 1])
    with left:
        render_ingredients(result, inputs)
    with right:
        st.subheader("Steps")
        for i, step in enumerate(writer.steps, 1):
            st.markdown(f"{i}. {step}")
        st.subheader("What will taste different")
        st.write(writer.taste_differences)

    render_substitutions(result, inputs)
    render_allergens(result, inputs)
    render_nutrition(result)
    render_trace(result)
    render_usage(result, saved_example)


if use_fixture:
    shown, shown_inputs, shown_seconds = load_example(FIXTURE_PATH)
else:
    shown, shown_inputs, shown_seconds = ss.result, ss.inputs, ss.elapsed
if shown is not None and shown.medical_context:
    st.info("HomeBite doesn't give medical advice; check with a registered dietitian.")
if shown is not None and shown.status == "blocked":
    st.info(shown.message)  # a friendly message, not an error
elif shown is not None and shown.status == "stopped":
    st.warning(shown.message)
    st.caption(f"Limit type: {shown.limit_kind}")
if shown is not None and shown.status in ("blocked", "stopped"):
    render_trace(shown)
    render_usage(shown, saved_example=use_fixture)
elif shown is not None and shown.status == "complete":
    render_result(shown, shown_inputs, saved_example=use_fixture, run_seconds=shown_seconds)

st.divider()
st.caption(
    "Nutrition values come from USDA FoodData Central. This is not medical advice. "
    "Grocery data is a starter set: products and prices are illustrative."
)
