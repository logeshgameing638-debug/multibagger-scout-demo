"""Headless UI tests (Streamlit AppTest) on SYNTHETIC data. They prove the floors render and are wired to the services, nothing about real markets."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from database.connection import make_session_factory, session_scope
from database.models import Decision, PaperOrder
from frontend import common as C
from tests.synthetic import DownProvider, FakeNews, FakeProvider

NAV = ["Building overview", "Floor 00 · Central Command", "Floor 01 · Market Scanner", "Floor 02 · AI Analyst", "Floor 03 · Risk Manager",
       "Floor 04 · Paper Executor (SIMULATED)", "Floor 05 · Monitor & Alerts", "Floor 06 · Portfolio Manager", "Floor 07 · Final Decision Engine"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    f = make_session_factory(f"sqlite:///{tmp_path / 'ui.db'}")
    monkeypatch.setattr(C, "factory", lambda: f)
    monkeypatch.setattr(C, "scheduler", lambda: None)
    monkeypatch.setattr(C, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(C, "get_news", lambda: FakeNews())
    monkeypatch.setattr("config.settings.EXPORT_DIR", (tmp_path / "exports").resolve())
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=90)
    at.f = f
    return at.run()


def goto(at, name):
    at.sidebar.radio(key="nav").set_value(name)
    return at.run()


def test_every_floor_renders_without_error(app):
    assert not app.exception
    for name in NAV:
        goto(app, name)
        assert not app.exception, (name, [e.value for e in app.exception])


def test_full_flow_analysis_risk_paper_portfolio_decision(app):
    goto(app, NAV[3])
    app.text_input(key="sym").set_value("testco")
    app.run()
    app.button(key="run_analysis").click().run()
    assert not app.exception and "analysis" in app.session_state
    r = app.session_state["analysis"]["out"]["result"]
    assert r["scores"] and all(a["status"] in ("ok", "partial") for a in r["agents"].values())
    goto(app, NAV[4])  # Floor 03 computes the assessment used by Floor 04
    assert not app.exception and app.session_state["assessment"]["label"] == "RESEARCH ONLY"
    goto(app, NAV[5])
    assert any("SIMULATED" in m.value for m in app.markdown)
    [b for b in app.button if b.label == "Place SIMULATED order"][0].click().run()
    assert not app.exception
    with session_scope(app.f) as s:
        orders = s.query(PaperOrder).all()
        assert len(orders) == 1 and orders[0].status in ("FILLED", "REJECTED")
        assert s.query(Decision).count() == 1
    for name in (NAV[7], NAV[8]):
        goto(app, name)
        assert not app.exception, (name, [e.value for e in app.exception])
    assert app.selectbox(key="dec_pick").value == "NSE:TESTCO"


def test_provider_outage_shows_error_not_fake_numbers(app, monkeypatch):
    monkeypatch.setattr(C, "get_provider", lambda: DownProvider())
    goto(app, NAV[3])
    app.text_input(key="sym").set_value("TESTCO")
    app.run()
    app.button(key="run_analysis").click().run()
    assert not app.exception
    assert any("Data provider failed" in e.value for e in app.error)
    assert "analysis" not in app.session_state or not app.session_state["analysis"]


def test_bad_symbol_is_rejected_in_ui(app):
    goto(app, NAV[3])
    app.text_input(key="sym").set_value("BAD;SYMBOL")
    app.run()
    app.button(key="run_analysis").click().run()
    assert any("Invalid input" in e.value for e in app.error)
