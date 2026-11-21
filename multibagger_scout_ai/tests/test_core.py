import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend
from agents import fundamental_agent, risk_agent, technical_agent
from config import settings
from data.validation import clean_ohlcv, validate_symbol
from database.connection import make_session_factory, session_scope
from database.models import (AgentRun, DataSource, FinancialStatement, MarketPrice, ResearchReport, ResearchScore, RiskFinding)
from engine import decision_engine, ranking, risk_manager
from engine.orchestrator import analyze
from indicators import ta
from tests.synthetic import DownProvider, FakeNews, FakeProvider, make_prices


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(f"sqlite:///{tmp_path / 't.db'}")


# ---------- indicators ----------
def test_rsi_extremes():
    up = pd.Series(np.arange(1, 80, dtype=float))
    assert ta.rsi(up).iloc[-1] == 100
    assert ta.rsi(up[::-1].reset_index(drop=True)).iloc[-1] == 0


def test_ema_constant_and_macd_identity():
    assert ta.ema(pd.Series([5.0] * 40), 10).iloc[-1] == pytest.approx(5.0)
    c = make_prices(bars=200)["Close"]
    m = ta.macd(c)
    assert (m["hist"] - (m["macd"] - m["signal"])).abs().dropna().max() < 1e-12


def test_atr_constant_range_and_adx_trend():
    c = pd.Series(100.0, index=range(60))
    assert ta.atr(c + 1, c - 1, c).iloc[-1] == pytest.approx(2.0)
    t = pd.Series(np.arange(1, 101, dtype=float))
    a = ta.adx(t + 0.5, t - 0.5, t)
    assert 40 < a["adx"].iloc[-1] <= 100 and a["plus_di"].iloc[-1] > a["minus_di"].iloc[-1]


def test_swing_points_exclude_unconfirmed_tail():
    p = make_prices(bars=120)
    ph, pl = ta.swing_points(p["High"], p["Low"], 5)
    assert ph.index.max() <= p.index[-6] and pl.index.max() <= p.index[-6]


# ---------- validation ----------
def test_symbol_validation():
    assert validate_symbol(" reliance.ns ") == "RELIANCE" and validate_symbol("500325") == "500325"
    for bad in ("", "REL;DROP TABLE", "../etc", "A" * 40, None):
        with pytest.raises(ValueError):
            validate_symbol(bad)


def test_clean_ohlcv_drops_bad_rows():
    d = make_prices(bars=50)
    d.iloc[3, d.columns.get_loc("Close")] = -1
    d = pd.concat([d, d.iloc[[10]]])
    clean, issues = clean_ohlcv(d)
    assert len(clean) == 49 and len(issues) == 2
    with pytest.raises(ValueError):
        clean_ohlcv(pd.DataFrame())


# ---------- fundamentals / scoring rules ----------
def test_fundamental_math_and_missing_stays_none():
    m = fundamental_agent.run(FakeProvider().fetch("T", "NSE"))["data"]["metrics"]
    assert m["sales_cagr_3y"] == pytest.approx((1330 / 870) ** (1 / 3) - 1)
    assert m["roe"] == pytest.approx(150 / 900) and m["roce"] == pytest.approx(220 / 1200)
    assert m["debt_to_equity"] == pytest.approx(200 / 900) and m["current_ratio"] == pytest.approx(2.0)
    assert m["sales_cagr_5y"] is None and m["profit_cagr_5y"] is None  # only 4 periods exist: must not be invented


def test_scores_bounded_explained_and_missing_earns_nothing(factory, tmp_path):
    r = analyze("TESTCO", "NSE", provider=FakeProvider(), news=FakeNews(), session_factory=factory, export_dir=tmp_path / "o")
    sc = r["scores"]
    for k in ("fundamental", "technical", "data_confidence"):
        assert 0 <= sc[k]["score"] <= 100 and sum(c["max"] for c in sc[k]["components"]) == 100
    assert sc["fundamental"]["assessable_points"] <= 75  # promoter + industry data unavailable -> 0 points, not full marks
    assert sc["data_confidence"]["score"] <= 81
    unassessed = [p for c in sc["fundamental"]["components"] for p in c["parts"] if p["points"] is None]
    assert unassessed and all(p["note"] for p in unassessed)


def test_financial_company_not_judged_by_industrial_rules():
    r = analyze("BANKCO", "NSE", provider=FakeProvider(financial=True), news=FakeNews(), persist=False, export=False)
    f, v, rk = (r["agents"][k]["data"] for k in ("fundamental", "valuation", "risk"))
    assert f["is_financial"] and f["metrics"]["debt_to_equity"] is None
    assert "Justified P/B" in v["method"] and "leverage" not in rk["assessed_checks"]


# ---------- risk ----------
M = dict(latest_equity=100.0, debt_to_equity=0.2, interest_coverage=9.0, operating_cash_flow=50.0, cash_conversion=1.0, sales_growth_1y=0.1,
         shares_outstanding_growth=0.0)
SCOUT = {"avg_traded_value_20d_inr": 1e9, "last_price_date": "2026-11-18"}


def run_risk(m, news=None):
    return risk_agent.run({}, SCOUT, {"metrics": m, "is_financial": False, "latest_annual_period": "2026-03-31"}, {}, news if news is not None else {}, {})["data"]


def test_negative_equity_is_critical():
    d = run_risk({**M, "latest_equity": -5.0})
    assert d["risk_class"] == "CRITICAL" and d["critical_alert"]


def test_headlines_alone_never_critical_and_flagged_unverified():
    hits = [{"headline": f"Auditor resigns at X {i}", "published_at": "2026-11-10T00:00:00+00:00"} for i in range(3)]
    d = run_risk(M, {"governance_hits": hits})
    g = [f for f in d["findings"] if f["category"] == "governance_news"][0]
    assert g["verified"] is False and g["severity"] in ("MODERATE", "HIGH") and d["risk_class"] != "CRITICAL"


def test_too_little_data_is_unassessed_not_low():
    d = risk_agent.run({}, {}, {}, {}, {}, {})["data"]
    assert d["risk_class"] == "UNASSESSED" and d["unassessed_checks"]


# ---------- technical ----------
def test_trend_direction_and_provisional_bar():
    up = technical_agent.run(make_prices(drift=0.002), None)["data"]["trend"]["daily"]
    dn = technical_agent.run(make_prices(drift=-0.002), None)["data"]["trend"]["daily"]
    assert up == "Bullish" and dn == "Bearish"
    p = make_prices(bars=300, end=pd.Timestamp("2026-11-18"))
    ist = timezone(timedelta(hours=5, minutes=30))
    done, prov = technical_agent.split_provisional(p, datetime(2026, 11, 18, 12, 0, tzinfo=ist))
    assert len(done) == 299 and len(prov) == 1
    done, prov = technical_agent.split_provisional(p, datetime(2026, 11, 18, 16, 0, tzinfo=ist))
    assert len(done) == 300 and prov.empty


# ---------- orchestrator, persistence, reports ----------
def test_end_to_end_persistence_and_reports(factory, tmp_path):
    out = tmp_path / "out"
    r = analyze("TESTCO", "NSE", provider=FakeProvider(), news=FakeNews(), session_factory=factory, export_dir=out)
    assert all(a["status"] in ("ok", "partial") for a in r["agents"].values()), {k: v["status"] for k, v in r["agents"].items()}
    assert len(r["agents"]) == 8 and r["provider"]["is_synthetic"] and any("SYNTHETIC" in w for w in r["warnings"])
    news = r["agents"]["news"]["data"]["items"]
    assert len(news) == 1 and news[0]["verification_status"] == "unverified_headline"  # duplicate merged, unrelated dropped
    hz = r["horizon_scores"]
    f, t = r["scores"]["fundamental"]["score"], r["scores"]["technical"]["score"]
    assert hz["long_term"] == pytest.approx(0.7 * f + 0.3 * t, abs=0.01) and hz["balanced"] == pytest.approx(0.5 * f + 0.5 * t, abs=0.02)
    html, js, cs = (Path(r["report_paths"][k]) for k in ("html", "json", "csv"))
    assert "SYNTHETIC TEST DATA" in html.read_text(encoding="utf-8") and "17. Sources" in html.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["symbol"] == "TESTCO" and cs.read_text(encoding="utf-8").startswith("path,value")
    assert html.name.startswith("SYNTHETIC_")
    with session_scope(factory) as s:
        n_prices, n_stmt = s.query(MarketPrice).count(), s.query(FinancialStatement).count()
        assert n_prices == len(r["_history"]) and n_stmt >= 16
        assert s.query(AgentRun).filter_by(run_id=r["run_id"]).count() == 8 and s.query(ResearchReport).count() == 3
        assert s.query(ResearchScore).one().is_synthetic is True
    analyze("TESTCO", "NSE", provider=FakeProvider(), news=FakeNews(), session_factory=factory, export_dir=out)
    with session_scope(factory) as s:  # re-run must not duplicate history
        assert s.query(MarketPrice).count() == n_prices and s.query(FinancialStatement).count() == n_stmt


def test_failed_provider_degrades_honestly(factory, tmp_path):
    r = analyze("TESTCO", "NSE", provider=DownProvider(), news=FakeNews(), session_factory=factory, export_dir=tmp_path / "o")
    st = {k: v["status"] for k, v in r["agents"].items()}
    assert st["stock_scout"] == "failed" and set(v for k, v in st.items() if k != "stock_scout") == {"skipped"}
    assert r["scores"] is None and r["horizon_scores"] is None and any("nothing was estimated" in w for w in r["warnings"])
    with session_scope(factory) as s:
        assert "simulated outage" in s.query(DataSource).filter_by(name="down_provider").one().last_error
        assert s.query(AgentRun).filter_by(run_id=r["run_id"], status="failed").count() == 1


def test_news_outage_does_not_stop_other_agents(factory, tmp_path):
    r = analyze("TESTCO", "NSE", provider=FakeProvider(), news=FakeNews(fail=True), session_factory=factory, export_dir=tmp_path / "o")
    assert r["agents"]["news"]["status"] == "failed" and any("'news' FAILED" in w for w in r["warnings"])
    assert r["scores"]["fundamental"] is not None and r["agents"]["risk"]["status"] in ("ok", "partial")
    assert "governance_news" not in r["agents"]["risk"]["data"]["assessed_checks"]


def test_missing_statements_give_no_fundamental_score_not_zero(tmp_path):
    r = analyze("TESTCO", "NSE", provider=FakeProvider(statements=False), news=FakeNews(), persist=False, export_dir=tmp_path / "o")
    assert r["agents"]["fundamental"]["status"] == "failed" and r["scores"]["fundamental"] is None and r["horizon_scores"]["balanced"] is None


# ---------- ranking + existing floors 03/07 contract ----------
def test_horizon_weights_and_critical_stays_visible():
    hz = ranking.horizon_scores(80, 40)
    assert (hz["long_term"], hz["short_term"], hz["balanced"]) == (68.0, 52.0, 60.0)
    mk = lambda sym, bal, rc: {"symbol": sym, "exchange": "NSE", "horizon_scores": {"balanced": bal, "long_term": bal, "short_term": bal}, "tags": [],
                               "scores": {"risk": {"class": rc, "score": 50}, "fundamental": {"score": bal}, "technical": {"score": bal}, "data_confidence": {"score": 60}}}
    rows = ranking.rank([mk("A", 50, "LOW"), mk("B", 90, "CRITICAL")])
    assert rows[0]["symbol"] == "B" and rows[0]["flag"] == "CRITICAL RISK"


def test_existing_risk_and_decision_floors_accept_orchestrator_output(tmp_path):
    r = analyze("TESTCO", "NSE", provider=FakeProvider(), news=FakeNews(), persist=False, export=False)
    assess = risk_manager.assess_trade(r, 1_000_000, 1.0, 10, 30, 0)
    dec = decision_engine.decide(r, assess)
    assert "verdict" in assess and dec and dec["verdict"] in ("APPROVE", "WATCHLIST", "REJECT")


# ---------- API ----------
def test_api(factory, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "EXPORT_DIR", (tmp_path / "exports").resolve())
    backend._hits.clear()
    backend.app.dependency_overrides.update({backend.get_provider: lambda: FakeProvider(), backend.get_news: lambda: FakeNews(),
                                             backend.get_session_factory: lambda: factory})
    try:
        c = TestClient(backend.app)
        assert c.get("/health").json()["status"] == "ok"
        r = c.post("/analyze", json={"symbol": "testco", "exchange": "NSE"})
        assert r.status_code == 200 and r.json()["agent_status"]["scoring"] in ("ok", "partial") and r.json()["provider"]["is_synthetic"]
        assert c.post("/analyze", json={"symbol": "BAD;SYM", "exchange": "NSE"}).status_code == 422
        assert c.post("/analyze", json={"symbol": "X", "exchange": "NYSE"}).status_code == 422
        assert c.get("/reports/TESTCO/html").status_code == 200
        with session_scope(factory) as s:  # a stored path outside the export folder must never be served
            s.add(ResearchReport(run_id="x", symbol="EVIL", exchange="NSE", fmt="html", path="/etc/passwd"))
        assert c.get("/reports/EVIL/html").status_code == 404
        monkeypatch.setattr(settings, "RATE_LIMIT_PER_MIN", 2)
        backend._hits.clear()
        codes = [c.get("/scores").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
    finally:
        backend.app.dependency_overrides.clear()


# ---------- scheduler ----------
def test_scheduler_builds_weekday_job(factory):
    from services import scheduler
    sch = scheduler.build_scheduler(factory, job=lambda: None)
    sch.start(paused=True)
    try:
        nxt = scheduler.next_run(sch)
        assert nxt is not None and nxt.weekday() < 5 and (nxt.hour, nxt.minute) == (18, 30)
    finally:
        sch.shutdown(wait=False)
