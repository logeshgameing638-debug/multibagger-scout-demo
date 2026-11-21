"""RPC layer: maps custom-UI actions to the archive's own services/engine/database calls. No rendering here."""
import base64
import os
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from sqlalchemy import inspect as sa_inspect

from config import settings
from config.logging_setup import setup_logging
from database.connection import init_db, make_session_factory, session_scope
from database.models import (Alert, Decision, FloorActivity, PaperOrder, PaperPosition, PipelineRun, PriceAlertRule, ResearchReport, RiskFinding,
                             ScanItem)
from engine import decision_engine, paper_broker, report_generator, risk_manager
from engine.pipeline import deep_research, run_daily_pipeline
from indicators import ta
from services import activity, automation_agent, command, monitor, notifier, portfolio, scanner, settings_store, tasks, universe, watchlist
from services.serialization import to_jsonable

SYNTHETIC = os.environ.get("SCOUT_PROVIDER") == "synthetic"
ISOLATION = os.environ.get("SCOUT_ISOLATION") == "visitor"  # per-visitor workspaces, no shared state
FLOOR_NAMES = activity.FLOORS

_FACTORY = None
_VFACTORIES = {}
_SCHED = None
_tls = threading.local()
_MAX_VISITOR_DBS = 25
_VLOCK = threading.Lock()
_VACTIVE = {}  # vid -> in-flight request count; an active workspace is never evicted
_VUSE = {}     # vid -> last request time, for LRU choice among idle workspaces


def _clean_vid(v):
    """Visitor ids become bare alphanumeric tokens, so they can never escape visitors/ as a path."""
    v = re.sub(r"[^a-zA-Z0-9]", "", str(v or ""))[:32]
    return v or None


def _vid():
    """Current visitor id (thread-local, set by dispatch) when isolation is on; else None."""
    if not ISOLATION:
        return None
    return _clean_vid(getattr(_tls, "vid", None))


def _active_inc(vid):
    with _VLOCK:
        _VACTIVE[vid] = _VACTIVE.get(vid, 0) + 1
        _VUSE[vid] = time.time()


def _active_dec(vid):
    with _VLOCK:
        _VACTIVE[vid] = max(0, _VACTIVE.get(vid, 1) - 1)
        _VUSE[vid] = time.time()


def _evict_visitor_dbs(vdir, keep):
    """Bound the scratchpad count: drop least-recently-used IDLE visitor DBs beyond the cap.
    A DB with an in-flight request, or the current visitor's, is never evicted; if too many
    workspaces are active at once the cap is exceeded rather than breaking a live visitor."""
    with _VLOCK:
        all_dbs = list(vdir.glob("*.db"))
        victims = sorted((p for p in all_dbs if p.stem != keep and _VACTIVE.get(p.stem, 0) == 0),
                         key=lambda p: _VUSE.get(p.stem, p.stat().st_mtime))
        excess = len(all_dbs) - _MAX_VISITOR_DBS + 1
        for victim in victims[:max(0, excess)]:
            _VFACTORIES.pop(victim.stem, None)
            victim.unlink(missing_ok=True)


def factory():
    global _FACTORY
    vid = _vid()
    if vid is None:
        if ISOLATION:
            raise RuntimeError("visitor id required in isolation mode")  # never silently bind a visitor to the shared DB
        if _FACTORY is None:
            setup_logging()
            _FACTORY = init_db()
        return _FACTORY
    f = _VFACTORIES.get(vid)
    if f is None:
        vdir = settings.ROOT / "visitors"
        vdir.mkdir(exist_ok=True)
        _evict_visitor_dbs(vdir, keep=vid)
        f = make_session_factory(f"sqlite:///{(vdir / (vid + '.db')).as_posix()}")
        _VFACTORIES[vid] = f
    return f


def _export_dir():
    vid = _vid()
    return settings.ROOT / "exports" / vid if vid else None


def scheduler():
    global _SCHED
    if ISOLATION:
        return None  # per-visitor workspaces: one in-process daily scheduler cannot serve every visitor DB
    if _SCHED is None:
        from services.scheduler import start_if_enabled
        _SCHED = start_if_enabled(factory()) or False
    return _SCHED or None


def get_provider():
    if SYNTHETIC:
        from synthetic import FakeProvider
        return FakeProvider()
    from data.connectors.yahoo import YahooConnector
    return YahooConnector()


def get_news():
    if SYNTHETIC:
        from synthetic import FakeNews
        return FakeNews()
    from data.connectors.rss_news import RssNewsConnector
    return RssNewsConnector()


def orm_rows(objs):
    objs = list(objs)
    if not objs:
        return []
    cols = [c.key for c in sa_inspect(type(objs[0])).mapper.column_attrs]
    return [{c: getattr(o, c) for c in cols} for o in objs]


def _err(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as exc:
        return {"error": str(exc)}


# ------------------------------------------------------------------ overview
def overview(e, st):
    f = factory()
    return {"floors": [dict(activity.floor_status(i, factory=f), index=i, name=FLOOR_NAMES[i]) for i in range(8)],
            "links": activity.active_links(60, factory=f)}


# ------------------------------------------------------------------ floor 00
def f00(e, st):
    f = factory()
    with session_scope(f) as s:
        run = s.query(PipelineRun).order_by(PipelineRun.id.desc()).first()
        last = None if run is None else {"id": run.id, "trigger": run.trigger, "status": run.status, "started": run.started_at,
                                         "finished": run.finished_at, "summary": run.summary}
    from services import scheduler as S
    sch = scheduler()
    keys = ("scheduler_enabled", "schedule_time", "batch_size", "time_budget_min", "deep_top_n", "refresh_universe")
    with session_scope(f) as s:
        row = s.query(FloorActivity).filter_by(event="automation_end").order_by(FloorActivity.id.desc()).first()
        auto = None if row is None else {"when": row.created_at, "payload": row.payload or {}}
    if auto and auto["payload"].get("digest"):
        auto["digest_text"] = automation_agent.digest_text(auto["payload"].get("status"), auto["payload"].get("run_id"), auto["payload"]["digest"])
    out = {"last_run": last, "next_run": None if not sch else S.next_run(sch), "scheduler_on": bool(sch),
           "coverage": scanner.coverage_summary(factory=f), "settings": {k: settings_store.get(k, f) for k in keys},
           "queue": tasks.queue_summary(f), "source_health": command.source_health(f), "db_health": command.db_health(f),
           "activity": activity.recent(limit=80, errors_only=bool(e.get("errors_only")), factory=f),
           "channels": notifier.configured(), "automation": auto}
    if ISOLATION:
        out["log_tail"] = None  # host log is shared across visitors and carries server paths - never exposed per visitor
        vf = settings.ROOT / "visitors" / (_vid() + ".db")
        out["db_health"]["size_mb"] = round(vf.stat().st_size / 1e6, 2) if vf.exists() else None  # own file, never the shared host DB
        out["workspace_note"] = ("Private session workspace: your watchlist, settings, simulated portfolio and reports are stored "
                                 "separately from other visitors. They reset when this visit ends or the app restarts. "
                                 "Host logs are hidden in multi-visitor mode and the scheduled daily run is off - run the pipeline manually.")
    else:
        out["log_tail"] = command.tail_log(60)
    return out


def run_pipeline(e, st):
    out = run_daily_pipeline(provider=get_provider(), news=get_news(), trigger="manual", factory=factory())
    return {"pipeline": out}


def save_settings(e, st):
    t = str(e.get("schedule_time", "")).strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
        return {"error": "Time must look like 18:30"}
    f = factory()
    for k, v in (("scheduler_enabled", str(bool(e.get("scheduler_enabled"))).lower()), ("schedule_time", t),
                 ("batch_size", e.get("batch_size")), ("time_budget_min", e.get("time_budget_min")),
                 ("deep_top_n", e.get("deep_top_n")), ("refresh_universe", str(bool(e.get("refresh_universe"))).lower())):
        settings_store.put(k, str(v), f)
    return {"saved": True}


def backup_db(e, st):
    if _vid():
        factory()  # make sure this visitor's DB exists
        src = settings.ROOT / "visitors" / (_vid() + ".db")
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            with sqlite3.connect(src) as con:
                dst = sqlite3.connect(tf.name)
                con.backup(dst)  # consistent snapshot without touching shared files
                dst.close()
            blob = open(tf.name, "rb").read()
        st["downloads"] = [{"label": "Download your workspace backup (.db)",
                            "name": f"workspace_{_vid()}.db", "data": base64.b64encode(blob).decode(),
                            "mime": "application/octet-stream", "b64": True}]
        return {"backup": "Your own workspace backup is ready below. It contains only your session data."}
    return {"backup": str(command.backup_database())}


def run_automation(e, st):
    # backup=False in isolation: the archive's backup targets the shared host DB path; visitors use their own backup button
    automation_agent.run_cycle(provider=get_provider(), news=get_news(), factory=factory(), probe_delay_s=3, backup=not ISOLATION)
    return {"ran": True}


# ------------------------------------------------------------------ floor 01
def f01(e, st):
    f = factory()
    with session_scope(f) as s:
        cnt = universe.counts(s)
        cov = scanner.coverage_summary(factory=f)
        items = []
        if cov:
            items = orm_rows(s.query(ScanItem).filter_by(cycle_id=cov["cycle_id"]).order_by(ScanItem.id).limit(500))
        wl = watchlist.entries(s)
    return {"counts": cnt, "coverage": cov, "scan_items": items, "watchlist": wl}


def download_nse(e, st):
    if SYNTHETIC:
        # demo mode must not probe the exchange website (automated access is restricted); say so truthfully
        out = f01(e, st)
        out["message"] = ("The direct NSE list download is disabled in this demo: no external data source is contacted. "
                          "Upload an official NSE or BSE listing CSV instead.")
        return out
    with session_scope(factory()) as s:
        msg = universe.import_csv(s, universe.download_nse(), "NSE", "NSE official equity list (manual download)")
    out = f01(e, st)
    out["message"] = msg
    return out


def upload_csv(e, st):
    data = base64.b64decode(e["content_b64"])
    ex = e.get("exchange", "NSE")
    with session_scope(factory()) as s:
        msg = universe.import_csv(s, data, ex, f"uploaded file {e.get('name', 'listing.csv')}")
    out = f01(e, st)  # return refreshed screen data so counts update immediately
    out["message"] = msg
    return out


def scan_batch(e, st):
    f = factory()
    cov = scanner.coverage_summary(factory=f)
    cid = cov["cycle_id"] if cov and cov["status"] != "complete" else scanner.start_cycle(f)
    return {"batch": scanner.run_batch(cid, get_provider(), settings_store.get_int("batch_size", f),
                                       settings_store.get_int("time_budget_min", f) * 60, None, f)}


def watchlist_add(e, st):
    err = _err(lambda: _wl_add(e))
    if "error" in err:
        return err
    out = f01(e, st)
    out["added"] = True
    return out


def _wl_add(e):
    with session_scope(factory()) as s:
        watchlist.add(s, e["symbol"], e.get("exchange", "NSE"))


# ------------------------------------------------------------------ floor 02
def _chart_payload(symbol, exchange):
    try:
        h = get_provider().fetch_history(symbol, exchange, period="2y")
    except Exception:
        return None
    if h is None or len(h) == 0:
        return None
    emas = {n: ta.ema(h["Close"], n) for n in (20, 50, 200)}
    tail = h.tail(400)
    idx = tail.index
    return {"dates": [d.isoformat()[:10] for d in idx],
            "o": list(tail["Open"]), "h": list(tail["High"]), "l": list(tail["Low"]), "c": list(tail["Close"]),
            "ema": {str(n): [None if i not in emas[n].index else emas[n][i] for i in idx] for n in (20, 50, 200)},
            "last_bar": str(idx[-1].date())}


def research(e, st):
    from data.connectors.base import ProviderError
    from data.validation import validate_exchange, validate_symbol
    try:
        sym, ex = validate_symbol(e["symbol"]), validate_exchange(e.get("exchange", "NSE"))
    except ValueError as exc:
        return {"error": f"Invalid input: {exc}"}
    try:
        out = deep_research(ex, sym, get_provider(), get_news(), factory())
    except ProviderError as exc:
        st.pop("analysis", None)
        st.pop("assessment", None)
        return {"error": f"Data provider failed: {exc}. Nothing was estimated. Try again later; the daily pipeline also retries failed stocks."}
    st["analysis"] = out
    st.pop("assessment", None)
    st.pop("downloads", None)
    chart = _chart_payload(sym, ex) if out["coverage"] != "unavailable" else None
    return {"result": out["result"], "coverage": out["coverage"], "decision": out["decision"], "assessment": out["assessment"],
            "chart": chart, "symbol": sym, "exchange": ex}


def make_report(e, st):
    an = st.get("analysis")
    if not an:
        return {"error": "Run a research on Floor 02 first."}
    r = an["result"]
    paths = report_generator.export_all(r, out_dir=_export_dir())
    with session_scope(factory()) as s:
        for fmt, p in paths.items():
            s.add(ResearchReport(run_id=r["run_id"], symbol=r["symbol"], exchange=r["exchange"], fmt=fmt, path=p))
    mimes = {"html": "text/html", "json": "application/json", "csv": "text/csv"}
    st["downloads"] = [{"label": f"Download {fmt.upper()}", "name": Path(p).name, "data": Path(p).read_text(encoding="utf-8"),
                        "mime": mimes[fmt]} for fmt, p in paths.items()]
    return {"paths": paths, "contents": {fmt: Path(p).read_text(encoding="utf-8") for fmt, p in paths.items()}}


# ------------------------------------------------------------------ floor 03
def f03(e, st):
    with session_scope(factory()) as s:
        findings = orm_rows(s.query(RiskFinding).order_by(RiskFinding.id.desc()).limit(50))
    an = st.get("analysis")
    cur = None
    if an and an["result"].get("scores"):
        r = an["result"]
        cur = {"risk": r["agents"]["risk"]["data"], "assessment": st.get("assessment") or an.get("assessment"),
               "symbol": an["result"]["symbol"]}
    return {"findings": findings, "current": cur,
            "defaults": {k: settings_store.get_float(k, factory()) for k in ("paper_capital", "risk_per_trade_pct", "max_position_pct", "max_sector_pct")}}


def assess(e, st):
    an = st.get("analysis")
    if not an:
        return {"error": "Run a research on Floor 02 first."}
    a = risk_manager.assess_trade(an["result"], float(e["capital"]), float(e["risk_pct"]), float(e["max_position_pct"]),
                                  float(e["max_sector_pct"]), 0.0)
    st["assessment"] = a
    return {"assessment": a}


# ------------------------------------------------------------------ floor 04
def f04(e, st):
    with session_scope(factory()) as s:
        out = {"open": orm_rows(s.query(PaperPosition).filter_by(status="OPEN")),
               "orders": orm_rows(s.query(PaperOrder).order_by(PaperOrder.id.desc()).limit(100)),
               "closed": orm_rows(s.query(PaperPosition).filter(PaperPosition.status != "OPEN").order_by(PaperPosition.id.desc()).limit(100))}
    an, a = st.get("analysis"), st.get("assessment")
    d = {}
    if an and an["result"]["agents"]["stock_scout"]["status"] in ("ok", "partial"):
        d = an["result"]["agents"]["stock_scout"]["data"]
    out["defaults"] = {"symbol": (an["result"]["symbol"] if an else ""), "exchange": (an["result"]["exchange"] if an else "NSE"),
                       "qty": int((a or {}).get("qty") or 0), "price": float(d.get("last_price") or 0.0),
                       "stop": float((a or {}).get("stop") or 0.0), "target": float((a or {}).get("target") or 0.0),
                       "sector": d.get("sector"), "price_date": str(d.get("last_price_date") or "")}
    return out


def place_order(e, st):
    an = st.get("analysis")
    d = {}
    if an and an["result"]["agents"]["stock_scout"]["status"] in ("ok", "partial"):
        d = an["result"]["agents"]["stock_scout"]["data"]
    f = factory()
    with session_scope(f) as s:
        paper_broker.place_order(s, str(e["symbol"]).strip().upper(), e.get("exchange", "NSE"), e.get("side", "BUY"), int(e["qty"]),
                                 float(e.get("price") or 0) or None, d.get("last_price_date"), float(e.get("stop") or 0) or None,
                                 float(e.get("target") or 0) or None, d.get("sector"), settings_store.get_float("slippage_pct", f), f)
    out = f04(e, st)
    out["placed"] = True
    return out


def check_exits(e, st):
    with session_scope(factory()) as s:
        closed = paper_broker.check_exits(s, lambda sy, ex: get_provider().fetch_history(sy, ex, period="3mo"), factory())
    out = f04(e, st)
    out["exits"] = closed
    return out


# ------------------------------------------------------------------ floor 05
def f05(e, st):
    with session_scope(factory()) as s:
        return {"alerts": monitor.open_alerts(s), "rules": orm_rows(s.query(PriceAlertRule).order_by(PriceAlertRule.id.desc())),
                "watchlist": watchlist.entries(s)}


def ack_alert(e, st):
    with session_scope(factory()) as s:
        s.get(Alert, int(e["id"])).acknowledged = True
    return f05(e, st)


def add_price_rule(e, st):
    from data.validation import validate_exchange, validate_symbol

    def _add():
        with session_scope(factory()) as s:
            s.add(PriceAlertRule(symbol=validate_symbol(e["symbol"]), exchange=validate_exchange(e.get("exchange", "NSE")),
                                 direction=e.get("direction", "above"), price=float(e["price"])))
        return {"added": True}
    out = _err(_add)
    if "error" in out:
        return out
    return f05(e, st)


def check_price_rules(e, st):
    with session_scope(factory()) as s:
        n = len(monitor.check_price_rules(s, get_provider()))
    out = f05(e, st)
    out["fired"] = n
    return out


# ------------------------------------------------------------------ floor 06
def f06(e, st):
    with session_scope(factory()) as s:
        return {"summary": portfolio.summary(s, get_provider() if e.get("refresh") else None, factory()),
                "performance": portfolio.performance(s)}


def snapshot(e, st):
    with session_scope(factory()) as s:
        portfolio.snapshot(s, None, factory())
    return f06({}, st)


# ------------------------------------------------------------------ floor 07
def f07(e, st):
    with session_scope(factory()) as s:
        seen, rows = set(), []
        for d in s.query(Decision).order_by(Decision.id.desc()):
            if (d.symbol, d.exchange) in seen:
                continue
            seen.add((d.symbol, d.exchange))
            rows.append(orm_rows([d])[0])
    rows.sort(key=lambda x: (x.get("balanced") is None, -(x.get("balanced") or 0)))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
        x["critical_flag"] = "CRITICAL RISK" if x.get("risk_class") == "CRITICAL" else ""
    return {"thresholds": decision_engine.THRESH, "rows": rows}


def report_files(e, st):
    with session_scope(factory()) as s:
        reps = s.query(ResearchReport).filter_by(symbol=e["symbol"], exchange=e["exchange"]).order_by(ResearchReport.id.desc()).limit(3).all()
        out = []
        for rp in reps:
            p = Path(rp.path)
            if p.exists():
                out.append({"fmt": rp.fmt, "name": p.name, "content": p.read_text(encoding="utf-8")})
    mimes = {"html": "text/html", "json": "application/json", "csv": "text/csv"}
    st["downloads"] = [{"label": f"Download saved {r['fmt'].upper()}", "name": r["name"], "data": r["content"], "mime": mimes[r["fmt"]]}
                       for r in out]
    return {"reports": out}


ACTIONS = {"overview": overview, "f00": f00, "run_pipeline": run_pipeline, "save_settings": save_settings, "backup_db": backup_db,
           "run_automation": run_automation, "f01": f01, "download_nse": download_nse, "upload_csv": upload_csv, "scan_batch": scan_batch,
           "watchlist_add": watchlist_add, "research": research, "make_report": make_report, "f03": f03, "assess": assess,
           "f04": f04, "place_order": place_order, "check_exits": check_exits, "f05": f05, "ack_alert": ack_alert,
           "add_price_rule": add_price_rule, "check_price_rules": check_price_rules, "f06": f06, "snapshot": snapshot,
           "f07": f07, "report_files": report_files}


def dispatch(event, st):
    vid = _clean_vid(event.get("vid"))
    if ISOLATION and not vid:
        return {"error": "workspace session identity missing - reload the app"}
    _tls.vid = vid
    if ISOLATION:
        _active_inc(vid)
    try:
        fn = ACTIONS.get(event.get("action"))
        if fn is None:
            return {"error": f"unknown action {event.get('action')}"}
        return fn(event, st)
    finally:
        if ISOLATION:
            _active_dec(vid)
        _tls.vid = None
