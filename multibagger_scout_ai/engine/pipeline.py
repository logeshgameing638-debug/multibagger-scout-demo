"""Daily research pipeline (scheduled or manual). Batch research after market close, NOT continuous monitoring.
Steps: retry queue -> universe refresh -> resumable light scan -> deep research of shortlist -> decisions/alerts -> reports -> paper exits."""
import gc
import logging
import time

from data.connectors.base import ProviderError
from data.connectors.rss_news import RssNewsConnector
from data.connectors.yahoo import YahooConnector
from database.connection import session_scope
from database.models import Decision, PipelineRun, ResearchReport
from engine import decision_engine, paper_broker, report_generator, risk_manager
from engine.orchestrator import analyze
from services import monitor, portfolio, scanner, settings_store, tasks, universe
from services.activity import log_activity
from services.clock import utc_naive
from database.models import PaperPosition

log = logging.getLogger(__name__)
CORE = ("stock_scout", "fundamental", "technical", "valuation", "risk", "scoring")


def deep_research(exchange, symbol, provider, news, factory=None, now=None):
    """Floor 02 -> 03 -> 07 for one stock. Provider outages raise ProviderError so the task queue can retry."""
    log_activity(1, "handoff", f"{exchange}:{symbol} shortlisted for deep research", to_floor=2, factory=factory)
    r = analyze(symbol, exchange, provider=provider, news=news, persist=True, session_factory=factory, export=False, now=now)
    err = r["provider"].get("fetch_error")
    if err:
        if "no price data" in err:
            return {"result": r, "coverage": "unavailable", "decision": None, "assessment": None}
        log_activity(2, "analysis_failed", f"{symbol}: {err}", "error", run_id=r["run_id"], factory=factory)
        raise ProviderError(err)
    log_activity(2, "analysis_done", f"{symbol}: agents " + ", ".join(f"{k}={v['status']}" for k, v in r["agents"].items()), run_id=r["run_id"], to_floor=3, factory=factory)
    cap = settings_store.get_float("paper_capital", factory)
    with session_scope(factory) as s:
        sector = (r["agents"]["stock_scout"]["data"] or {}).get("sector")
        sector_value = sum(p.entry_price * p.qty for p in s.query(PaperPosition).filter_by(status="OPEN") if sector and p.sector == sector)
        assess = risk_manager.assess_trade(r, cap, settings_store.get_float("risk_per_trade_pct", factory), settings_store.get_float("max_position_pct", factory),
                                           settings_store.get_float("max_sector_pct", factory), sector_value)
    log_activity(3, "risk_assessed", f"{symbol}: {assess['verdict']} ({'; '.join(assess['reasons'][:2])})", run_id=r["run_id"], to_floor=7, factory=factory)
    dec = decision_engine.decide(r, assess)
    with session_scope(factory) as s:
        if dec:
            sc, hz = r["scores"], r["horizon_scores"]
            s.add(Decision(run_id=r["run_id"], symbol=symbol, exchange=exchange, verdict=dec["verdict"], reasons=dec["reasons"], risk_assessment=_clean(assess),
                           balanced=hz["balanced"], fundamental=sc["fundamental"]["score"], technical=sc["technical"]["score"],
                           data_confidence=sc["data_confidence"]["score"], risk=sc["risk"]["score"], risk_class=sc["risk"]["class"]))
        new_alerts = monitor.evaluate(s, r, dec)
    if dec:
        log_activity(7, "decision", f"{symbol}: {dec['verdict']} (balanced {r['horizon_scores']['balanced']:.1f})", run_id=r["run_id"], factory=factory)
    if new_alerts:
        log_activity(5, "alerts", f"{symbol}: {len(new_alerts)} new alert(s)", run_id=r["run_id"], factory=factory)
    cov = "complete" if all(r["agents"][a]["status"] in ("ok", "partial") for a in CORE) else "partial"
    r["_history"] = r["_statements"] = None  # free memory (4 GB machines)
    return {"result": r, "coverage": cov, "decision": dec, "assessment": assess}


def _clean(d):
    from services.serialization import to_jsonable
    return to_jsonable(d)


def run_daily_pipeline(provider=None, news=None, trigger="manual", factory=None, now=None):
    provider, news = provider or YahooConnector(), news or RssNewsConnector()
    g = lambda k: settings_store.get_int(k, factory)
    batch, budget_s, top_n = g("batch_size"), g("time_budget_min") * 60, g("deep_top_n")
    with session_scope(factory) as s:
        run = PipelineRun(trigger=trigger)
        s.add(run)
        s.flush()
        run_id = run.id
    log_activity(0, "pipeline_start", f"Daily research pipeline #{run_id} started ({trigger})", factory=factory)
    summ, errors = {"steps": {}}, []

    def step(name, fn):
        t0 = time.monotonic()
        try:
            out = fn()
            summ["steps"][name] = {"status": "ok", "seconds": round(time.monotonic() - t0, 1), "detail": out}
            return out
        except Exception as exc:
            log.exception("pipeline step %s failed", name)
            msg = f"{type(exc).__name__}: {exc}"
            summ["steps"][name] = {"status": "failed", "error": msg}
            errors.append(f"{name}: {msg}")
            log_activity(0, "step_failed", f"{name}: {msg}", "error", factory=factory)
            return None

    handlers = {"analyze_symbol": lambda p: deep_research(p["exchange"], p["symbol"], provider, news, factory, now)}
    step("retry_queue", lambda: tasks.run_queue(handlers, limit=50, factory=factory))
    if settings_store.get_bool("refresh_universe", factory):
        def refresh():
            with session_scope(factory) as s:
                return universe.import_csv(s, universe.download_nse(), "NSE", "NSE official equity list (auto-download)")
        step("universe_refresh", refresh)
    cycle_id = step("start_cycle", lambda: scanner.start_cycle(factory))
    if cycle_id:
        log_activity(1, "scan", f"Light scan of cycle #{cycle_id} started", factory=factory)
        step("light_scan", lambda: scanner.run_batch(cycle_id, provider, batch, budget_s, now, factory))
        cands = step("select_candidates", lambda: scanner.deep_candidates(cycle_id, top_n, factory)) or []
    else:  # empty universe: still research the watchlist
        cands = []
        from database.models import Watchlist
        with session_scope(factory) as s:
            cands = [(w.exchange, w.symbol) for w in s.query(Watchlist).filter_by(enabled=True)]
    done = []
    for ex, sym in cands:
        try:
            out = deep_research(ex, sym, provider, news, factory, now)
            if cycle_id:
                scanner.mark_deep(cycle_id, ex, sym, out["coverage"], out["result"]["run_id"], factory=factory)
            done.append(out)
        except Exception as exc:
            tasks.enqueue("analyze_symbol", {"exchange": ex, "symbol": sym}, factory=factory)
            errors.append(f"deep {ex}:{sym}: {exc} (queued for retry)")
        gc.collect()
    summ["deep_researched"] = len(done)

    def reports():
        ranked = sorted([d for d in done if d["decision"]], key=lambda d: -d["result"]["horizon_scores"]["balanced"])
        pick = ranked[:10] + [d for d in ranked[10:] if d["decision"]["verdict"] == "APPROVE"]
        with session_scope(factory) as s:
            for d in pick:
                r = d["result"]
                r["report_paths"] = report_generator.export_all(r)
                for fmt, p in r["report_paths"].items():
                    s.add(ResearchReport(run_id=r["run_id"], symbol=r["symbol"], exchange=r["exchange"], fmt=fmt, path=p))
        return len(pick)
    summ["reports_saved"] = step("reports", reports)

    def paper():
        with session_scope(factory) as s:
            closed = paper_broker.check_exits(s, lambda sy, ex: provider.fetch_history(sy, ex, period="3mo"), factory)
            fired = monitor.check_price_rules(s, provider)
            portfolio.snapshot(s, provider, factory)
        if closed:
            log_activity(4, "simulated_exit", "; ".join(f"{a} {b}" for a, b in closed), factory=factory)
        return {"simulated_exits": closed, "price_alerts": len(fired)}
    step("paper_and_price_alerts", paper)

    cov = scanner.coverage_summary(cycle_id, factory) if cycle_id else None
    summ["coverage"] = cov["text"] if cov else "No universe scan this run."
    summ["errors"] = errors
    pending = bool(cov and cov["pending"])
    status = "failed" if (not cycle_id and not cands) else "partial" if (errors or pending) else "complete"
    with session_scope(factory) as s:
        run = s.get(PipelineRun, run_id)
        run.status, run.finished_at, run.cycle_id = status, utc_naive(), cycle_id
        from services.serialization import to_jsonable
        run.summary = to_jsonable(summ)
    log_activity(0, "pipeline_end", f"Pipeline #{run_id} {status}. {summ['coverage']}", "ok" if status == "complete" else "error", factory=factory)
    return {"run_id": run_id, "status": status, **summ}
