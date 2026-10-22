"""Make the UI's saved example with ONE live run through the app's own code path (costs a few cents).

It drives app.py headlessly (Streamlit's AppTest), clicks "Adapt my dish", and saves the result together with the
settings and the run time to tests/fixtures/example_result.json.
"""

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pathlib import Path  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

from agents import save_example  # noqa: E402

ROOT = Path(__file__).resolve().parent
at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300).run()
at.multiselect[0].set_value(["peanuts"]).run()  # the store (Walmart) and servings (2) are the sidebar defaults
at.text_area(key="dish_text").set_value("Taiwanese beef noodle soup").run()
at.button[-1].click().run()

result, settings, seconds = at.session_state["result"], at.session_state["inputs"], at.session_state["elapsed"]
assert result is not None and result.status == "complete", f"unexpected result: {getattr(result, 'status', None)} {getattr(result, 'message', '')}"
# If the gateway answered from its cache (a few seconds, tokens identical to an earlier run), edit run_seconds to null by hand.
save_example(result, settings, seconds, ROOT / "tests" / "fixtures" / "example_result.json")
print("settings:", settings, "| seconds:", seconds, "| usage:", result.usage_total)
