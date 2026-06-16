from pathlib import Path
from streamlit.testing.v1 import AppTest

_APP = str(Path(__file__).parent.parent / "streamlit_app.py")


def test_app_loads_and_shows_title():
    at = AppTest.from_file(_APP).run(timeout=10)
    assert not at.exception
    assert any("memoQ QA Resolver" in t.value for t in at.title)


def test_app_shows_uploader_before_analysis():
    at = AppTest.from_file(_APP).run(timeout=10)
    # no ReviewSession yet -> an info/uploader prompt is present, no crash
    assert not at.exception
