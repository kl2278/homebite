"""A fake LLM for offline tests and the safety demo: PydanticAI's FunctionModel that answers per agent.

It spends no tokens. Each agent is recognised by a phrase from its system prompt.
"""

from collections import Counter, defaultdict

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

RICE, EGG = 168877, 171287  # USDA fdc_ids: raw white rice, raw egg

GOOD_WRITER = {
    "intro": "A simple rice bowl for two, adapted to your store.",
    "steps": ["Cook 200 g rice for about 15 minutes.", "Fry 100 g egg until set.",
              "Stir in 20 g Huy Fong Chili Garlic Sauce 18 oz and serve."],
    "taste_differences": "The chili garlic sauce is a little brighter than the original paste.",
}


def ingredient(name, grams, fdc_id, hard=False, role="starch"):
    return {"name": name, "grams_per_serving": grams, "role": role, "hard_to_find_abroad": hard, "fdc_id": fdc_id}


BASE_DISH = [
    ingredient("white rice", 100, RICE),
    ingredient("egg", 50, EGG, role="protein"),
    ingredient("chili bean paste", 10, None, hard=True, role="sauce"),
]
CHILI_SUB = {"substitutions": [{
    "original_name": "chili bean paste", "status": "substituted", "product_name": "Huy Fong Chili Garlic Sauce 18 oz",
    "taste_texture_note": "Brighter and less fermented.", "reason": "Closest sauce at this store.", "closest_option_or_skip": None}]}


class FakeLLM:
    def __init__(self, guard="ok", dish=None, substitutions=None, writer=None, request=None, clarify=None,
                 analyst_calls=None, loop_analyst=False):
        self.guard, self.dish = guard, dish or BASE_DISH
        self.substitutions = list(substitutions or [CHILI_SUB])  # one entry per substitution call; last repeats
        self.writer = list(writer or [GOOD_WRITER])  # one entry per writer call; last repeats
        self.request = request or {"dish_name": "Egg rice bowl", "cuisine_origin": "Chinese", "servings": 2, "goals": []}
        self.clarify, self.analyst_calls, self.loop_analyst = clarify, analyst_calls, loop_analyst
        self.calls, self.prompts = Counter(), defaultdict(list)

    def model(self) -> FunctionModel:
        return FunctionModel(self._respond)

    @staticmethod
    def _final(info, data, suffix=None):
        tool = next(t for t in info.output_tools if suffix is None or t.name.endswith(suffix))
        return ModelResponse(parts=[ToolCallPart(tool.name, data)])

    def _respond(self, messages, info):
        text = info.instructions or ""
        first = messages[0]
        prompt = " ".join(p.content for p in first.parts if isinstance(p, UserPromptPart))
        has_tool_result = any(isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", []))

        if "classify a student's message" in text:
            agent = "guard"
            response = self._final(info, {"category": self.guard, "reason": "fake classifier"})
        elif "turn a student's message" in text:
            agent = "intake"
            response = (self._final(info, {"question": self.clarify}, "ClarifyingQuestion") if self.clarify
                        else self._final(info, self.request, "Request"))
        elif "cooking expert" in text:
            agent = "analyst"
            if self.loop_analyst or (self.analyst_calls and not has_tool_result):
                n = self.analyst_calls or 1
                response = ModelResponse(parts=[ToolCallPart("search_nutrition", {"query": "rice"}) for _ in range(n)])
            elif not has_tool_result:
                response = ModelResponse(parts=[ToolCallPart("search_nutrition", {"query": q}) for q in ("white rice raw", "egg raw")])
            else:
                response = self._final(info, {"ingredients": self.dish})
        elif "local substitutes" in text:
            agent = "substitution"
            index = min(self.calls["substitution"], len(self.substitutions) - 1)
            response = self._final(info, self.substitutions[index])
        elif "warm, concise answer" in text:
            agent = "writer"
            index = min(self.calls["writer"], len(self.writer) - 1)
            response = self._final(info, self.writer[index])
        else:
            raise AssertionError("unknown agent: " + text[:60])
        self.calls[agent] += 1
        self.prompts[agent].append(prompt)
        return response
