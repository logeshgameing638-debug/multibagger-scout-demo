from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from database.connection import make_session_factory, session_scope
from database.models import Company, ExchangeSymbol, FloorActivity, MarketPrice, PipelineRun
from frontend import common as C
from services import automation_agent as A, notifier, settings_store, watchlist
from services.clock import utc_naive
from tests.synthetic import DownProvider, FakeNews, FakeProvider

OK_PIPE = lambda: {"status": "complete", "run_id": 99, "coverage": "Deep-researched 1 of 1", "errors": []}


@pytest.fixture
def f(tmp_path, monkeypatch):
    monkeypatch.setattr("config.settings.EXPORT_DIR", (tmp_path / "exp").resolve())
    fac = make_session_factory(f"sqlite:///{tmp_path / 'a.db'}")
    settings_store.put("refresh_universe", "false", fac)
    with session_scope(fac) as s:
        watchlist.add(s, "TESTCO", "NSE")
    return fac


def seed_price(fac, day):  # the injected fake pipeline stores nothing, so give the freshness check one stored bar
    with session_scope(fac) as s:
        co = Company(name="SEED")
        s.add(co)
        s.flush()
        es = ExchangeSymbol(company_id=co.id, exchange="NSE", symbol="SEED")
        s.add(es)
        s.flush()
        s.add(MarketPrice(symbol_id=es.id, trade_date=day, interval="1d", open=1, high=1, low=1, close=1, volume=1, source="t"))


@pytest.fixture
def posts(monkeypatch):
    calls = []

    class R:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(notifier.requests, "post", lambda url, **kw: calls.append((url, kw)) or R())
    return calls


def test_healthy_cycle_runs_real_pipeline_and_notifies(f, posts):
    c = A.run_cycle(provider=FakeProvider(), news=FakeNews(), factory=f, probe_delay_s=0, backup=False, env={"NTFY_TOPIC": "abc123"})
    assert c["status"] in ("complete", "partial") and c["probe"]["ok"] and c["run_id"] and A.exit_code(c) == 0
    assert c["digest"]["decisions"] >= 1 and c["digest"]["latest_price_date"] and not c["digest"]["stale"]
    assert len(posts) == 1 and posts[0][0] == "https://ntfy.sh/abc123"
    body = posts[0][1]["data"].decode()
    assert f"run #{c['run_id']}" in body and "Research only" in body
    with session_scope(f) as s:
        assert s.query(FloorActivity).filter_by(event="automation_end").one().payload["run_id"] == c["run_id"]


def test_provider_down_skips_pipeline_and_says_so(f, posts):
    dp = DownProvider()
    c = A.run_cycle(provider=dp, news=FakeNews(), factory=f, probe_retries=2, probe_delay_s=0, backup=False, env={"WEBHOOK_URL": "https://hooks.example/x"})
    assert c["status"] == "skipped_provider_down" and dp.history_calls == 3 and A.exit_code(c) == 1
    with session_scope(f) as s:
        assert s.query(PipelineRun).count() == 0  # pipeline never ran
    assert "NOT run" in posts[0][1]["json"]["text"] and "nothing was estimated" in posts[0][1]["json"]["text"]


def test_second_start_is_blocked_but_stale_running_row_is_ignored(f):
    with session_scope(f) as s:
        s.add(PipelineRun(trigger="manual", status="running", started_at=utc_naive()))
    busy = A.run_cycle(provider=FakeProvider(), factory=f, backup=False, pipeline=OK_PIPE, env={})
    assert busy["status"] == "skipped_busy" and busy["probe"] is None and A.exit_code(busy) == 0
    with session_scope(f) as s:
        s.query(PipelineRun).update({"started_at": utc_naive() - timedelta(hours=5)})
    seed_price(f, datetime.now())
    assert A.run_cycle(provider=FakeProvider(), factory=f, backup=False, pipeline=OK_PIPE, env={})["status"] == "complete"


def test_crash_is_retried_once_then_reported_failed(f):
    n = []

    def boom():
        n.append(1)
        raise RuntimeError("db exploded")

    c = A.run_cycle(provider=FakeProvider(), factory=f, probe_delay_s=0, cycle_retries=1, backup=False, pipeline=boom, env={})
    assert len(n) == 2 and c["status"] == "failed" and "db exploded" in c["message"] and A.exit_code(c) == 1
    seed_price(f, datetime.now())
    seq = iter([{"status": "failed", "run_id": 1, "coverage": "", "errors": ["x"]}, OK_PIPE()])
    c = A.run_cycle(provider=FakeProvider(), factory=f, probe_delay_s=0, cycle_retries=1, backup=False, pipeline=lambda: next(seq), env={})
    assert c["status"] == "complete"


def test_stale_stored_prices_downgrade_status_and_are_flagged(f, posts):
    with session_scope(f) as s:
        co = Company(name="X")
        s.add(co)
        s.flush()
        es = ExchangeSymbol(company_id=co.id, exchange="NSE", symbol="X")
        s.add(es)
        s.flush()
        s.add(MarketPrice(symbol_id=es.id, trade_date=datetime(2026, 11, 1), interval="1d", open=1, high=1, low=1, close=1, volume=1, source="t"))
    c = A.run_cycle(provider=FakeProvider(), factory=f, backup=False, pipeline=OK_PIPE, today=date(2026, 11, 20), env={"NTFY_TOPIC": "abc"})
    assert c["digest"]["stale"] and c["status"] == "partial" and "STALE" in posts[0][1]["data"].decode()


def test_notifier_all_channels_never_leak_secrets_and_never_raise(monkeypatch, posts):
    sent = []

    class Srv:
        def __init__(self, host, port, timeout=None):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        starttls = lambda self: sent.append("tls")
        login = lambda self, u, p: sent.append(("login", u))
        send_message = lambda self, m: sent.append(("mail", m["To"]))

    monkeypatch.setattr(notifier.smtplib, "SMTP", Srv)
    env = {"NTFY_TOPIC": "topic-1", "TELEGRAM_BOT_TOKEN": "TOKEN123", "TELEGRAM_CHAT_ID": "42", "WEBHOOK_URL": "https://hooks.example/s3cr3t",
           "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "me", "SMTP_PASSWORD": "pw-xyz", "SMTP_TO": "me@example.com"}
    assert notifier.configured(env) == ["ntfy", "telegram", "email", "webhook"]
    res = notifier.send("hello", env=env)
    assert all(r["ok"] for r in res) and "tls" in sent and ("mail", "me@example.com") in sent and len(posts) == 3
    assert any(k[0].startswith("https://api.telegram.org/botTOKEN123") for k in posts)

    def explode(url, **kw):
        raise RuntimeError(f"cannot reach {url}")

    monkeypatch.setattr(notifier.requests, "post", explode)
    res = notifier.send("hello", env=env)
    blob = str(res)
    assert not any(s in blob for s in ("TOKEN123", "s3cr3t", "topic-1", "pw-xyz")) and sum(not r["ok"] for r in res) == 3 and [r for r in res if r["channel"] == "email"][0]["ok"]
    assert notifier.send("x", env={}) == [] and notifier.configured({"NTFY_TOPIC": "  "}) == []
    bad = notifier.send("x", env={"WEBHOOK_URL": "http://insecure.example"})
    assert not bad[0]["ok"] and "https" in bad[0]["error"]
    assert len(posts) == 3  # nothing sent over plain http
    monkeypatch.setattr(notifier.requests, "post", lambda url, **kw: posts.append((url, kw)) or type("R", (), {"raise_for_status": lambda s: None})())
    notifier.send("y" * 9000, env={"NTFY_TOPIC": "abc"})
    assert len(posts[-1][1]["data"].decode()) <= 3500


def test_floor00_automation_panel_runs_a_cycle(tmp_path, monkeypatch):
    fac = make_session_factory(f"sqlite:///{tmp_path / 'u.db'}")
    settings_store.put("refresh_universe", "false", fac)
    with session_scope(fac) as s:
        watchlist.add(s, "TESTCO", "NSE")
    for k in ("NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "WEBHOOK_URL", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("config.settings.EXPORT_DIR", (tmp_path / "exp").resolve())
    monkeypatch.setattr(C, "factory", lambda: fac)
    monkeypatch.setattr(C, "scheduler", lambda: None)
    monkeypatch.setattr(C, "get_provider", lambda: FakeProvider())
    monkeypatch.setattr(C, "get_news", lambda: FakeNews())
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=120).run()
    at.sidebar.radio(key="nav").set_value("Floor 00 · Central Command").run()
    assert not at.exception and at.button(key="auto_test").disabled  # no channel configured -> button disabled
    at.button(key="auto_run").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Last automation cycle" in x.value for x in list(at.success) + list(at.error))
