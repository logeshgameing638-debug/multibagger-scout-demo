"""Automation agent: supervises one unattended daily cycle. Rule-based (no LLM).
check busy -> probe data provider (retry) -> run the daily pipeline (re-run once if it fails) -> check data freshness ->
build a digest -> back up SQLite -> notify. It reports problems; it never hides them and never estimates missing data."""
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import func

from config import settings
from database.connection import get_factory, session_scope
from database.models import Alert, Decision, MarketPrice, PipelineRun
from services import notifier
from services.activity import log_activity
from services.clock import utc_naive

log = logging.getLogger(__name__)
FAIL_STATUSES = ("failed", "skipped_provider_down")
DISCLAIMER = "Research only, not advice. Free end-of-day data; may be delayed."


def exit_code(cycle):
    """0 = completed or partial, 1 = nothing useful happened (lets GitHub/Task Scheduler flag the run)."""
    return 1 if cycle["status"] in FAIL_STATUSES else 0


def _busy(factory, hours):
    with session_scope(factory) as s:
        return s.query(PipelineRun).filter(PipelineRun.status == "running", PipelineRun.started_at >= utc_naive() - timedelta(hours=hours)).first() is not None


def _probe(provider, symbol, exchange, retries, delay):
    last = "no attempt made"
    for i in range(retries + 1):
        try:
            h = provider.fetch_history(symbol, exchange, period="5d")
            if h is not None and len(h) > 0:
                return {"ok": True, "attempts": i + 1, "last_bar": h.index[-1].date().isoformat(), "symbol": symbol}
            last = "provider returned no rows"
        except Exception as exc:
            last = notifier._scrub(f"{type(exc).__name__}: {exc}", {})
        if i < retries:
            time.sleep(delay)
    return {"ok": False, "attempts": retries + 1, "error": last, "symbol": symbol}


def _max_id(s, model):
    return s.query(func.max(model.id)).scalar() or 0


def build_digest(factory, p, before_decision, before_alert, today):
    with session_scope(factory) as s:
        decs = s.query(Decision).filter(Decision.id > before_decision).all()
        alerts = s.query(Alert).filter(Alert.id > before_alert).all()
        latest = s.query(func.max(MarketPrice.trade_date)).scalar()
        approve = sorted([d for d in decs if d.verdict == "APPROVE"], key=lambda d: -(d.balanced or 0))[:5]
        d = {"approve": [(x.exchange, x.symbol, round(x.balanced or 0, 1)) for x in approve],
             "critical": sorted({(x.exchange, x.symbol) for x in decs if x.risk_class == "CRITICAL"}),
             "decisions": len(decs), "alerts": len(alerts), "alert_kinds": {}}
        for a in alerts:
            d["alert_kinds"][a.kind] = d["alert_kinds"].get(a.kind, 0) + 1
    d["latest_price_date"] = latest.date().isoformat() if latest else None
    d["stale"] = bool(latest and (today - latest.date()).days > settings.STALE_DAYS)
    d["no_prices_stored"] = latest is None
    d["pipeline_status"], d["coverage"], d["errors"] = p.get("status"), p.get("coverage"), list(p.get("errors") or [])
    return d


def digest_text(status, run_id, d):
    L = [f"Multibagger Scout AI | run #{run_id} | {status.upper()}", f"Coverage: {d.get('coverage') or 'n/a'}"]
    L.append("Latest stored price date: " + (d["latest_price_date"] or "none stored") + ("  ** STALE **" if d.get("stale") else ""))
    L.append("APPROVE (worth deeper study): " + (", ".join(f"{e}:{s} ({b})" for e, s, b in d["approve"]) or "none this run"))
    if d["critical"]:
        L.append("CRITICAL risk: " + ", ".join(f"{e}:{s}" for e, s in d["critical"]))
    L.append(f"New alerts: {d['alerts']}" + (" (" + ", ".join(f"{k} {v}" for k, v in d["alert_kinds"].items()) + ")" if d["alert_kinds"] else ""))
    for e in d["errors"][:5]:
        L.append("Problem: " + e[:160])
    L.append(DISCLAIMER)
    return "\n".join(L)


def run_cycle(provider=None, news=None, factory=None, notify=True, probe_retries=None, probe_delay_s=None, cycle_retries=None,
              backup=True, today=None, pipeline=None, env=None):
    from data.connectors.rss_news import RssNewsConnector
    from data.connectors.yahoo import YahooConnector
    provider, news, factory = provider or YahooConnector(), news or RssNewsConnector(), factory or get_factory()
    pr = settings.PROBE_RETRIES if probe_retries is None else probe_retries
    pd_ = settings.PROBE_DELAY_S if probe_delay_s is None else probe_delay_s
    cr = settings.CYCLE_RETRIES if cycle_retries is None else cycle_retries
    today = today or datetime.now().date()
    out = {"started_at": datetime.now().isoformat(timespec="seconds"), "status": None, "probe": None, "run_id": None, "digest": None,
           "message": None, "notifications": [], "backup": None, "channels": notifier.configured(env)}
    log_activity(0, "automation_start", "Automation cycle started", factory=factory)

    def finish(status, message, text=None, ok=True):
        out.update(status=status, message=message)
        if notify and text:
            out["notifications"] = notifier.send(text, title=f"Scout AI: {status}", env=env)
        log_activity(0, "automation_end", f"{status}: {message}"[:300], "ok" if ok else "error", payload={k: out[k] for k in ("status", "probe", "digest", "notifications", "backup", "message", "run_id")}, factory=factory)
        return out

    if _busy(factory, settings.BUSY_HOURS):
        return finish("skipped_busy", "another pipeline run is in progress; this cycle did not start a second one")
    out["probe"] = _probe(provider, settings.PROBE_SYMBOL, "NSE", pr, pd_)
    if not out["probe"]["ok"]:
        msg = f"Data provider did not answer after {out['probe']['attempts']} attempts ({out['probe']['error']}). The pipeline was NOT run and nothing was estimated."
        return finish("skipped_provider_down", msg, f"Multibagger Scout AI | cycle skipped\n{msg}\n{DISCLAIMER}", ok=False)
    with session_scope(factory) as s:
        b_dec, b_alert = _max_id(s, Decision), _max_id(s, Alert)
    run = pipeline
    if run is None:
        from engine.pipeline import run_daily_pipeline
        run = lambda: run_daily_pipeline(provider=provider, news=news, trigger="scheduled", factory=factory)
    p, err = None, None
    for attempt in range(cr + 1):
        try:
            p = run()
            err = None
            if p["status"] != "failed":
                break
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            log.exception("automation: pipeline crashed")
        if attempt < cr:
            time.sleep(pd_)
    if p is None:
        msg = f"Pipeline crashed: {err}"
        return finish("failed", msg, f"Multibagger Scout AI | cycle FAILED\n{msg}\n{DISCLAIMER}", ok=False)
    out["run_id"] = p["run_id"]
    d = build_digest(factory, p, b_dec, b_alert, today)
    status = p["status"]
    if d["stale"] or d["no_prices_stored"]:
        d["errors"].append("Stored price data is stale or missing: scores may rest on old data." if d["stale"] else "No prices stored yet.")
        status = "partial" if status == "complete" else status
    out["digest"] = d
    if backup:
        try:
            from services import command
            out["backup"] = str(command.backup_database())
        except FileNotFoundError:
            out["backup"] = "skipped (not a local SQLite database)"
        except Exception as exc:
            out["backup"] = f"failed: {exc}"
            d["errors"].append(f"Database backup failed: {exc}")
    return finish(status, p.get("coverage") or "", digest_text(status, p["run_id"], d), ok=status != "failed")
