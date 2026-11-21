"""Floor 01 Market Scanner: resumable batch scan of the whole universe (RAM-safe: one stock at a time, nothing cached).
Stage 'light' = price/volume/momentum + technical score for every stock. Stage 'deep' (pipeline) = all agents for shortlisted stocks."""
import gc
import logging
import time

from agents import scoring_agent, technical_agent
from data.connectors.base import NoDataError, ProviderError
from data.validation import clean_ohlcv
from database.connection import session_scope
from database.models import ScanCycle, ScanItem, Watchlist
from services import universe
from services.activity import log_activity
from services.clock import utc_naive

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def start_cycle(factory=None):
    """Resume the running cycle if there is one; otherwise create a new cycle from the current universe."""
    with session_scope(factory) as s:
        cyc = s.query(ScanCycle).filter_by(status="running").order_by(ScanCycle.id.desc()).first()
        if cyc:
            return cyc.id
        stocks = universe.scan_list(s)
        if not stocks:
            raise ValueError("The stock universe is empty. Import the NSE/BSE lists on Floor 01 first.")
        cyc = ScanCycle(total=len(stocks))
        s.add(cyc)
        s.flush()
        s.bulk_insert_mappings(ScanItem, [{"cycle_id": cyc.id, "exchange": x["exchange"], "symbol": x["symbol"], "name": x["name"], "state": "pending"} for x in stocks])
        cid = cyc.id
    log_activity(1, "cycle_started", f"New scan cycle #{cid}: {len(stocks)} stocks", factory=factory)
    return cid


def light_scan(provider, exchange, symbol, now=None):
    hist = provider.fetch_history(symbol, exchange)
    clean, issues = clean_ohlcv(hist)
    out = {"data_date": clean.index[-1].date().isoformat(), "light_score": None, "momentum_3m": None}
    c = clean["Close"]
    if len(c) > 63:
        out["momentum_3m"] = float(c.iloc[-1] / c.iloc[-64] - 1)
    traded = float((c.tail(20) * clean["Volume"].tail(20)).mean())
    out["avg_traded_value"] = traded
    out["liquidity_class"] = "HIGH" if traded >= 1e8 else "ADEQUATE" if traded >= 1e7 else "LOW"
    try:
        tech = technical_agent.run(clean, now)
        out["light_score"] = scoring_agent.technical(tech["data"])["score"]
    except ValueError:  # too few bars (recent listing): price data exists but indicators cannot be computed
        out["note"] = "fewer than 30 completed daily bars"
    return out


def run_batch(cycle_id, provider, batch_size=50, time_budget_s=None, now=None, factory=None):
    t0, processed = time.monotonic(), {"done": 0, "unavailable": 0, "partial": 0, "failed": 0}
    while True:
        with session_scope(factory) as s:
            items = (s.query(ScanItem).filter(ScanItem.cycle_id == cycle_id, (ScanItem.state == "pending") | ((ScanItem.state == "failed") & (ScanItem.attempts < MAX_ATTEMPTS)))
                     .order_by(ScanItem.id).limit(batch_size).all())
            todo = [(i.id, i.exchange, i.symbol) for i in items]
        if not todo:
            break
        for iid, ex, sym in todo:
            if time_budget_s is not None and time.monotonic() - t0 > time_budget_s:
                return {**processed, "stopped": "time budget reached; will resume next run"}
            try:
                r = light_scan(provider, ex, sym, now)
                upd = {"state": "done", "coverage": "partial", "stage": "light", "error": r.get("note"), **{k: r[k] for k in ("data_date", "light_score", "momentum_3m", "avg_traded_value", "liquidity_class")}}
                processed["partial"] += 1
            except NoDataError as exc:
                upd, key = {"state": "done", "coverage": "unavailable", "error": str(exc)}, "unavailable"
                processed[key] += 1
            except ProviderError as exc:
                upd = {"state": "failed", "error": str(exc)}
                processed["failed"] += 1
            except Exception as exc:  # one bad stock must never stop the batch
                upd = {"state": "failed", "error": f"{type(exc).__name__}: {exc}"}
                processed["failed"] += 1
            with session_scope(factory) as s:
                it = s.get(ScanItem, iid)
                it.attempts += 1
                it.updated_at = utc_naive()
                for k, v in upd.items():
                    setattr(it, k, v)
            processed["done"] += 1
            gc.collect() if processed["done"] % 25 == 0 else None
    with session_scope(factory) as s:
        cyc = s.get(ScanCycle, cycle_id)
        left = s.query(ScanItem).filter(ScanItem.cycle_id == cycle_id, (ScanItem.state == "pending") | ((ScanItem.state == "failed") & (ScanItem.attempts < MAX_ATTEMPTS))).count()
        if left == 0 and cyc.status == "running":
            cyc.status, cyc.finished_at = "complete", utc_naive()
    return {**processed, "stopped": None}


def deep_candidates(cycle_id, top_n, factory=None):
    """Watchlist first, then best price-scan scores among adequately liquid stocks. Skips stocks already deep-researched this cycle."""
    with session_scope(factory) as s:
        watch = [(w.exchange, w.symbol) for w in s.query(Watchlist).filter_by(enabled=True)]
        ranked = (s.query(ScanItem).filter(ScanItem.cycle_id == cycle_id, ScanItem.state == "done", ScanItem.light_score.isnot(None),
                                           ScanItem.liquidity_class != "LOW", ScanItem.stage == "light")
                  .order_by(ScanItem.light_score.desc()).limit(top_n).all())
        picks = list(dict.fromkeys(watch + [(i.exchange, i.symbol) for i in ranked]))
        done = {(i.exchange, i.symbol) for i in s.query(ScanItem).filter(ScanItem.cycle_id == cycle_id, ScanItem.stage == "deep")}
    return [p for p in picks if p not in done]


def mark_deep(cycle_id, exchange, symbol, coverage, run_id, error=None, factory=None):
    with session_scope(factory) as s:
        it = s.query(ScanItem).filter_by(cycle_id=cycle_id, exchange=exchange, symbol=symbol).one_or_none()
        if it is None:  # watchlist stock outside the universe list: still tracked
            it = ScanItem(cycle_id=cycle_id, exchange=exchange, symbol=symbol)
            s.add(it)
        it.state, it.coverage, it.stage, it.run_id, it.error, it.updated_at = "done", coverage, "deep", run_id, error, utc_naive()


def coverage_summary(cycle_id=None, factory=None):
    with session_scope(factory) as s:
        cyc = s.get(ScanCycle, cycle_id) if cycle_id else s.query(ScanCycle).order_by(ScanCycle.id.desc()).first()
        if cyc is None:
            return None
        q = s.query(ScanItem).filter(ScanItem.cycle_id == cyc.id)
        n = lambda **kw: q.filter_by(**kw).count()
        total = q.count()
        out = {"cycle_id": cyc.id, "status": cyc.status, "started_at": cyc.started_at, "total": total, "pending": n(state="pending"),
               "failed": n(state="failed"), "price_scanned": q.filter(ScanItem.stage.isnot(None)).count(),
               "deep_complete": n(stage="deep", coverage="complete"), "deep_partial": n(stage="deep", coverage="partial"),
               "unavailable": n(coverage="unavailable")}
        out["text"] = (f"Deep-researched {out['deep_complete']} of {total} stocks; price-scanned {out['price_scanned']} of {total}; "
                       f"{out['unavailable']} have no data; {out['failed']} failed (retried up to {MAX_ATTEMPTS}x); {out['pending']} pending.")
        return out
