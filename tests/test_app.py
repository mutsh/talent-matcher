"""Smoke tests for the UI: every tab renders and every order can be matched, with no Gemini key."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / "app.py")


def test_all_tabs_render_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Match an order", "Add talent (AI extraction)",
                                          "Eligibility matrix", "Rules and data"]
    assert next(b for b in at.button if b.label == "Extract with AI").disabled   # AI off without a key


def test_every_order_can_be_matched(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    for i in range(len(at.selectbox[0].options)):
        at.selectbox[0].select_index(i).run()
        next(b for b in at.button if b.label == "Run match").click().run()
        assert not at.exception and at.metric, f"order #{i} produced no suggestions"
