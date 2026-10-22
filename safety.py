"""Safety and cost controls: input screening, usage caps, output checks.

Everything here is plain code (the one classifier call lives in agents.py and is passed in).
All limits are named constants at the top.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

import tools
import usage

# ================================================================ limits (edit here)

MAX_INPUT_CHARS = 1000  # longest student text accepted (a long recipe description is ~500)
RATE_LIMIT_RUNS = 20  # runs allowed per session per window
RATE_LIMIT_WINDOW_SECONDS = 3600  # the window for the rate limit: one hour
RUN_TOKEN_CAP = 100_000  # input+output tokens for one run (a normal run uses about 25,000)
SESSION_TOKEN_CAP = 800_000  # input+output tokens per browser session (about 30 normal runs)
DAILY_TOKEN_CAP = 3_000_000  # input+output tokens per UTC day across all sessions, read from logs/usage.jsonl

# Per-agent limits: model requests and tool calls in one agent run. Normal runs use far less.
GUARD_REQUEST_LIMIT = 2
INTAKE_REQUEST_LIMIT = 4
ANALYST_REQUEST_LIMIT = 10  # the example used 4 requests
ANALYST_TOOL_CALL_LIMIT = 45  # the example used 27 tool calls
SUBSTITUTION_REQUEST_LIMIT = 8  # the example used 2 requests
SUBSTITUTION_TOOL_CALL_LIMIT = 6
WRITER_REQUEST_LIMIT = 6  # includes the output-validator retries

SAFETY_LOG_PATH = Path(__file__).resolve().parent / "logs" / "safety_events.jsonl"

# A harmless marker put in every system prompt. If it ever shows up in an answer, a prompt leaked.
CANARY = "HB-CANARY-4c1e9a"


# ================================================================ input screening

Category = Literal["ok", "injection", "medical_advice", "medical_context", "extreme_restriction", "off_topic"]


class GuardVerdict(BaseModel):
    """Output of the cheap classifier call."""

    category: Category
    reason: str


class ScreenResult(BaseModel):
    allowed: bool
    category: str  # ok, injection, off_topic, medical_advice, extreme_restriction, medical_context, too_long, empty
    caught_by: Literal["length", "rule", "classifier", "none"]
    message: str = ""
    medical_context: bool = False
    rule: str = ""
    reason: str = ""


class GuardUnavailable(Exception):
    """The classifier could not be used, so the request must not run (fail closed)."""


MESSAGES = {
    "injection": "I can only help adapt a dish from home to the ingredients at your store. "
                 "Please describe the dish you'd like to cook.",
    "settings": "Your store and allergies come from the sidebar settings, not from the text box. "
                "Please change them in the sidebar and describe your dish again.",
    "off_topic": "I can only help adapt dishes from home to ingredients you can buy near you. "
                 "Tell me about a dish you'd like to cook.",
    "medical_advice": "HomeBite can't give medical or diet advice for health conditions, so I can't plan this one. "
                      "A doctor or a registered dietitian is the right person to ask. "
                      "I'm happy to adapt a dish if you tell me what you'd like to cook.",
    "extreme_restriction": "It sounds like food might feel really hard right now, and I'm not able to help with extreme "
                           "restriction. Please consider talking to a doctor or a registered dietitian. The National "
                           "Alliance for Eating Disorders runs a helpline; you can find their current contact details "
                           "by searching for their name. You deserve support.",
    "too_long": f"That's a bit long for me. Please keep it under {MAX_INPUT_CHARS} characters.",
    "empty": "Please tell me about a dish from home first.",
}

STORES_RE = r"(walmart|trader joe'?s?|whole foods|aldi|asian grocery)"
# (rule name, message key, pattern). Cheap and run first, before any LLM call.
INPUT_RULES = [
    ("instruction_override", "injection",
     r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b(previous|prior|above|earlier|all|any|your|the|these|my)?\s*"
     r"(instructions?|rules?|prompts?|guidelines?|restrictions?|safety)"),
    ("role_change", "injection", r"\byou are now\b|\bdeveloper mode\b|\bjailbreak\b|\bdo anything now\b|\bpretend (you are|to be|you have no)\b"),
    ("prompt_leak", "injection",
     r"\b(reveal|show|print|repeat|display|output|leak|tell me|give me|what('s| is| are))\b.{0,40}"
     r"\b(system prompt|your (instructions|prompt|rules|guidelines)|initial prompt|hidden prompt)"),
    ("secrets", "injection",
     r"\b(api[ _-]?keys?|secret keys?|access tokens?|auth tokens?|environment variables?|env vars?|passwords?|credentials?|portkey)\b"
     r"|\.env\b|\bsk-[A-Za-z0-9]|[A-Z]+_API_KEY"),
    ("choose_store", "settings",
     rf"\b(search|check|use|switch( to)?|look (at|in)|change (the |my )?store( to)?)\b.{{0,25}}\b{STORES_RE}\b"
     rf"|\b{STORES_RE}\b.{{0,15}}\binstead\b"),
    ("change_allergies", "settings",
     r"\b(ignore|forget|disregard|remove|drop|skip|without checking)\b.{0,25}\b(my |the |any )?allerg(y|ies|ens?)\b"
     r"|\bnot allergic\b|\bno allergies\b|\bi('m| am) allergic to nothing\b"),
]
_COMPILED_RULES = [(name, key, re.compile(pattern, re.IGNORECASE)) for name, key, pattern in INPUT_RULES]


def rule_check(text: str) -> tuple[str, str] | None:
    """Return (rule name, message key) for the first matching input rule, else None."""
    for name, key, pattern in _COMPILED_RULES:
        if pattern.search(text):
            return name, key
    return None


KEY_LIKE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}|\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b|portkey|[A-Z]+_API_KEY", re.IGNORECASE)


def log_safety_event(category: str, caught_by: str, text: str, path: Path | None = None) -> None:
    """Append one blocked request to logs/safety_events.jsonl (first 100 characters only, key-like text removed)."""
    path = path or SAFETY_LOG_PATH
    path.parent.mkdir(exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "caught_by": caught_by,
        "input_start": KEY_LIKE.sub("[removed]", text)[:100],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def screen_input(text: str, classify: Callable[[str], GuardVerdict] | None, log_path: Path | None = None) -> ScreenResult:
    """Check the student's text before any agent runs: length, free rules, then one cheap classifier call."""

    def blocked(category: str, caught_by: str, key: str, **extra) -> ScreenResult:
        log_safety_event(category, caught_by, text, log_path)
        return ScreenResult(allowed=False, category=category, caught_by=caught_by, message=MESSAGES[key], **extra)

    if not text.strip():
        return ScreenResult(allowed=False, category="empty", caught_by="length", message=MESSAGES["empty"])
    if len(text) > MAX_INPUT_CHARS:
        return blocked("too_long", "length", "too_long")

    hit = rule_check(text)
    if hit:
        rule, key = hit
        return blocked("injection", "rule", key, rule=rule)

    if classify is None:
        return ScreenResult(allowed=True, category="ok", caught_by="none")
    try:
        verdict = classify(text)
    except LimitReached:
        raise  # a usage cap is not a classifier failure
    except Exception as error:  # fail closed: no classifier, no run
        raise GuardUnavailable(str(error)) from error

    if verdict.category in ("injection", "off_topic", "medical_advice", "extreme_restriction"):
        return blocked(verdict.category, "classifier", verdict.category, reason=verdict.reason)
    return ScreenResult(allowed=True, category=verdict.category, caught_by="classifier",
                        medical_context=verdict.category == "medical_context", reason=verdict.reason)


# ================================================================ usage caps

class LimitReached(Exception):
    """A cap tripped. kind says which one: rate, session, daily, run, or agent."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class SessionLimits:
    """Per-browser-session counters (kept in st.session_state by the UI)."""

    run_times: list[float] = field(default_factory=list)  # start time of each run
    tokens_used: int = 0


def total_tokens(entry: dict) -> int:
    return entry["input_tokens"] + entry["output_tokens"]


def daily_tokens(now: datetime | None = None, path: Path | None = None) -> int:
    """Tokens logged today (UTC), read from logs/usage.jsonl so a browser refresh doesn't reset it."""
    path = path or usage.LOG_PATH
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    total = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("timestamp", "").startswith(today):
                total += total_tokens(entry)
    return total


def check_can_start(session: SessionLimits, now: float | None = None, usage_path: Path | None = None) -> None:
    """Rate limit and token caps, checked before any LLM call. Raises LimitReached."""
    now = time.time() if now is None else now
    recent = [t for t in session.run_times if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_RUNS:
        wait_minutes = max(1, int((min(recent) + RATE_LIMIT_WINDOW_SECONDS - now) / 60) + 1)
        raise LimitReached("rate", f"Rate limit reached: {RATE_LIMIT_RUNS} runs per hour per session. "
                                   f"Please try again in about {wait_minutes} minute(s).")
    if session.tokens_used >= SESSION_TOKEN_CAP:
        raise LimitReached("session", "Session token limit reached. Please try again in a new session later.")
    if daily_tokens(path=usage_path) >= DAILY_TOKEN_CAP:
        raise LimitReached("daily", "HomeBite's daily usage limit has been reached. Please try again tomorrow.")
    session.run_times = recent + [now]


class RunBudget:
    """Token budget for one run. Call add() and check() after every stage."""

    def __init__(self, session: SessionLimits, usage_path: Path | None = None):
        self.session = session
        self.usage_path = usage_path
        self.run_tokens = 0

    def add(self, tokens: int) -> None:
        self.run_tokens += tokens
        self.session.tokens_used += tokens

    def check(self) -> None:
        if self.run_tokens > RUN_TOKEN_CAP:
            raise LimitReached("run", f"This request used more than the {RUN_TOKEN_CAP:,}-token limit for a single run, so it was stopped.")
        if self.session.tokens_used > SESSION_TOKEN_CAP:
            raise LimitReached("session", "Session token limit reached, so this request was stopped.")
        if daily_tokens(path=self.usage_path) > DAILY_TOKEN_CAP:
            raise LimitReached("daily", "HomeBite's daily usage limit has been reached, so this request was stopped.")


# ================================================================ output checks

@dataclass
class OutputFacts:
    """What the Writer is allowed to say, taken from the Verifier output."""

    allowed_numbers: set[float]  # ingredient amounts, servings, numbers inside ingredient/product names
    confirmed_products: set[str]  # substitute products confirmed at this store (lowercase)
    vocabulary: set[str]  # lowercase words from the dish, cuisine, ingredients, products and stores


NUMBER = r"\d+(?:[.,]\d+)?[½¼¾]?|[½¼¾]"
FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}
# Cooking numbers: times, temperatures and sizes ("1½-2 hours", "180 °C", "2 cm").
COOKING_SPAN = re.compile(
    rf"({NUMBER})(?:\s*(?:-|–|to)\s*({NUMBER}))?\s*-?\s*(?:minutes?|mins?|hours?|hrs?|seconds?|secs?|°|º|degrees?|cm|mm|inch(?:es)?)",
    re.IGNORECASE,
)
STEP_NUMBER = re.compile(r"\bstep\s*(\d+)|^\s*(\d+)[.)]\s", re.IGNORECASE)
NUTRITION_UNITS = re.compile(rf"({NUMBER})\s*(?:kcal|cal\b|calories|mg\b|milligrams?)", re.IGNORECASE)
# Nutrition talk: nutrient words, and claims about sugar/fat/salt. The plain ingredients "sugar" and "fat" are fine.
NUTRITION_WORDS = re.compile(
    r"kcal|calori|nutrition|protein|carb|sodium|\bfiber\b|\bfibre\b|"
    r"\b(low|high|less|more|reduced|lower|higher|rich|free|no|zero)[- ]+(in[- ]+)?(sugar|fat|salt)\b|"
    r"\b(sugar|fat|salt)[- ]*(free|content)\b|\bhealth(y|ier)\b|\bdiet(ary)? (friendly|food)\b",
    re.IGNORECASE,
)
CAPITALIZED = re.compile(r"\b[A-Z][A-Za-z'’\-]*(?:\s+[A-Z][A-Za-z'’\-]*)+\b")


def to_number(token: str) -> float:
    token = token.replace(",", ".")
    fraction = FRACTIONS.get(token[-1]) if token and token[-1] in FRACTIONS else None
    base = token[:-1] if fraction is not None else token
    return (float(base) if base else 0.0) + (fraction or 0.0)


def numbers_in(text: str) -> list[float]:
    return [to_number(t) for t in re.findall(NUMBER, text)]


def check_output(parts: list[str], facts: OutputFacts, prompt_texts: tuple[str, ...] = ()) -> list[str]:
    """Return a list of violations in the Writer's text (empty list = OK)."""
    text = "\n".join(parts)
    lowered = text.lower()
    violations = []

    # 1. Leaks: canary, system-prompt fragments, key-like strings.
    if CANARY.lower() in lowered:
        violations.append("The text contains the internal marker (a system prompt leaked).")
    for prompt in prompt_texts:
        words = re.findall(r"\w+", prompt.lower())
        shingles = {" ".join(words[i:i + 7]) for i in range(max(0, len(words) - 6))}
        if any(s in " ".join(re.findall(r"\w+", lowered)) for s in shingles):
            violations.append("The text repeats part of the system prompt.")
            break
    if KEY_LIKE.search(text):
        violations.append("The text contains a key-like string.")

    # 2. Nutrition: no nutrition words or nutrition-unit numbers at all.
    if NUTRITION_WORDS.search(text) or NUTRITION_UNITS.search(text):
        violations.append("The text mentions nutrition (calories, protein, fat, carbs, sodium, fiber, sugar or mg values).")

    # 3. Numbers must come from the Verifier output or be cooking numbers.
    cooking = set()
    for match in COOKING_SPAN.finditer(text):
        cooking.update(to_number(g) for g in match.groups() if g)
    for match in STEP_NUMBER.finditer(text):
        cooking.update(float(g) for g in match.groups() if g)
    invented = []
    for number in numbers_in(text):
        allowed = any(abs(number - a) < 0.05 for a in facts.allowed_numbers) or number in cooking
        if not allowed and number not in invented:
            invented.append(number)
    if invented:
        violations.append("These numbers are not in the verified ingredient data and are not cooking times or temperatures: "
                          + ", ".join(f"{n:g}" for n in invented))

    # 4. Products: only substitutes confirmed at this store.
    catalog_names = {i.product_name.lower() for i in tools._catalog()}
    stray = [n for n in catalog_names if n in lowered and n not in facts.confirmed_products]
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        for match in CAPITALIZED.finditer(sentence):
            words = match.group(0).split()
            at_start = match.start() == len(sentence) - len(sentence.lstrip())
            if at_start and len(words) < 3:
                continue
            if not all(re.sub(r"['’]s$", "", w.lower()) in facts.vocabulary for w in words):
                stray.append(match.group(0))
    if stray:
        violations.append("These look like product names that were not confirmed at this store: " + ", ".join(sorted(set(stray))))
    return violations
