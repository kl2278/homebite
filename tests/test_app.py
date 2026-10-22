"""UI flow tests with run_pipeline replaced by a fake (no LLM calls). Run: pytest"""

from pathlib import Path

import agents
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "example_result.json"


def new_app(monkeypatch, fake):
    monkeypatch.setattr(agents, "run_pipeline", fake)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def submit(at, text):
    at.text_area(key="dish_text").set_value(text).run()
    at.button[-1].click().run()


def test_saved_example_mode_shows_banner_and_results(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("saved-example mode must not call the pipeline")

    at = new_app(monkeypatch, fail)
    at.toggle(key="use_fixture").set_value(True).run()
    assert not at.exception
    assert any("saved example" in w.value for w in at.warning)
    assert len(at.metric) == 4


def test_error_shows_friendly_message_and_try_again(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    at = new_app(monkeypatch, boom)
    submit(at, "pho")
    assert not at.exception  # no raw traceback
    assert "Something went wrong" in at.error[0].value
    assert "secret internal detail" not in at.error[0].value
    at.button[-1].click().run()  # Try again
    assert not at.error


def test_clarifying_question_then_answer(monkeypatch):
    calls = []

    def fake(text, settings, progress_callback=None):
        calls.append(text)
        if len(calls) == 1:
            return agents.PipelineResult(status="needs_clarification", clarifying_question="Which dish?")
        return agents.load_result(FIXTURE)

    at = new_app(monkeypatch, fake)
    submit(at, "something from home")
    assert at.info[0].value == "Which dish?"
    at.text_input[0].set_value("beef noodle soup")
    at.button[-1].click().run()  # Continue
    assert "something from home" in calls[1] and "beef noodle soup" in calls[1]
    assert not at.exception
    assert len(at.metric) == 4
