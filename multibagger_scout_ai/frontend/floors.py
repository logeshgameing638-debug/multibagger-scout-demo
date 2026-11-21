"""One render function per floor. Every number comes from the database or a live provider call; gaps are shown as gaps."""
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database.connection import session_scope
from database.models import (Alert, Decision, PaperOrder, PaperPosition, PipelineRun, PriceAlertRule, ResearchReport, RiskFinding, ScanCycle, ScanItem)
from frontend import common as C
from indicators import ta
from services import activity, command, monitor, portfolio, scanner, settings_store, tasks, universe, watchlist
from services.serialization import to_jsonable

DELAY = "Data: Yahoo Finance via yfinance (unofficial, end-of-day / delayed). "


# ------------------------------------------------------------------ Floor 00
def floor00():
    f = C.factory()
    st.subheader("Floor 00 · Central Command")
    from services import scheduler as S
    sch = C.scheduler()
    with session_scope(f) as s:
        run = s.query(PipelineRun).order_by(PipelineRun.id.desc()).first()
        last = None if run is None else {"id": run.id, "trigger": run.trigger, "status": run.status, "started": run.started_at, "finished": run.finished_at, "summary": run.summary}
    cov = scanner.coverage_summary(factory=f)
    a, b, c = st.columns(3)
    a.markdown(f"<div class='card'>Last run<br><b>{last['status'].upper() if last else 'NEVER'}</b><br><span class='dim'>{last['started'] if last else 'no run recorded'}</span></div>", unsafe_allow_html=True)
    nxt = S.next_run(sch)
    b.markdown(f"<div class='card'>Next scheduled run<br><b>{nxt.strftime('%a %d %b %H:%M IST') if nxt else 'NOT SCHEDULED'}</b><br><span class='dim'>{'scheduler running in this process' if sch else 'scheduler disabled'}</span></div>", unsafe_allow_html=True)
    c.markdown(f"<div class='card'>Coverage<br><b>{cov['deep_complete'] if cov else 0} of {cov['total'] if cov else 0}</b><br><span class='dim'>stocks deep-researched in latest cycle</span></div>", unsafe_allow_html=True)
    if cov:
        st.caption(cov["text"])
    C.banner("This is scheduled batch research from end-of-day data, not continuous monitoring. The scheduler only fires while this app and the computer running it are on. "
             "A sleeping free-hosted app cannot schedule itself: unattended runs need an external runner plus a durable database (see DEPLOY_ONLINE.md). Otherwise use manual runs.")
    if st.button("Run pipeline now", key="run_pipeline", help="Runs the whole daily pipeline once. Can take a long time on a large universe."):
        from engine.pipeline import run_daily_pipeline
        with st.spinner("Pipeline running (this can take many minutes)..."):
            try:
                out = run_daily_pipeline(provider=C.get_provider(), news=C.get_news(), trigger="manual", factory=f)
                (st.success if out["status"] == "complete" else st.warning)(f"Pipeline #{out['run_id']} finished: {out['status'].upper()}. {out.get('coverage', '')}")
                for e in out.get("errors", []):
                    st.error(e)
            except Exception as exc:
                st.error(f"Pipeline crashed: {type(exc).__name__}: {exc}")
    if last and last["summary"]:
        with st.expander("Last pipeline run: step results"):
            st.json(to_jsonable(last["summary"]))
    _automation_panel(f)
    with st.expander("Schedule and batch settings"):
        with st.form("settings_form"):
            en = st.checkbox("Scheduler enabled", settings_store.get_bool("scheduler_enabled", f))
            t = st.text_input("Run time (IST, HH:MM, Mon-Fri). Restart the app to apply.", settings_store.get("schedule_time", f))
            batch = st.number_input("Batch size (stocks per batch)", 1, 500, settings_store.get_int("batch_size", f))
            budget = st.number_input("Time budget per run (minutes)", 1, 600, settings_store.get_int("time_budget_min", f))
            top = st.number_input("Deep-research top N", 1, 200, settings_store.get_int("deep_top_n", f))
            ref = st.checkbox("Refresh NSE universe list at each run", settings_store.get_bool("refresh_universe", f))
            if st.form_submit_button("Save settings"):
                if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t.strip()):
                    st.error("Time must look like 18:30")
                else:
                    for k, v in (("scheduler_enabled", str(en).lower()), ("schedule_time", t.strip()), ("batch_size", batch), ("time_budget_min", budget), ("deep_top_n", top), ("refresh_universe", str(ref).lower())):
                        settings_store.put(k, v, f)
                    st.success("Saved.")
    l, r = st.columns(2)
    with l:
        st.markdown("**Task queue (retries)**")
        q = tasks.queue_summary(f)
        st.write(q["counts"])
        C.table(q["recent"])
        st.markdown("**Data source health**")
        C.table(command.source_health(f))
    with r:
        st.markdown("**Database health**")
        h = command.db_health(f)
        st.write({"integrity": h["integrity"], "ok": h["ok"], "size_mb": h["size_mb"]})
        C.table([{"table": k, "rows": v} for k, v in h["tables"].items()])
        if st.button("Back up database now", key="backup"):
            try:
                st.success(f"Backup written: {command.backup_database()}")
            except Exception as exc:
                st.error(f"Backup failed: {exc}")
    st.markdown("**Agent communication and activity log**")
    errs = st.toggle("Errors only", key="errs_only")
    C.table(activity.recent(limit=80, errors_only=errs, factory=f))
    with st.expander("Application log (last lines)"):
        st.code("\n".join(command.tail_log(60)) or "empty")


# ------------------------------------------------------------------ Floor 01
def floor01():
    f = C.factory()
    st.subheader("Floor 01 · Market Scanner")
    with session_scope(f) as s:
        cnt = universe.counts(s)
    st.write(f"Universe: **{cnt['NSE']}** NSE and **{cnt['BSE']}** BSE listings imported; **{cnt['to_scan']}** will be scanned (BSE duplicates of NSE ISINs skipped).")
    if cnt["NSE"] + cnt["BSE"] == 0:
        C.banner("The universe is empty, so no market-wide scan can run. Download the NSE list below, or upload an official NSE/BSE listing CSV. Nothing is guessed.")
    c1, c2 = st.columns(2)
    if c1.button("Download NSE equity list", key="dl_nse"):
        try:
            with session_scope(f) as s:
                st.success(universe.import_csv(s, universe.download_nse(), "NSE", "NSE official equity list (manual download)"))
        except Exception as exc:
            st.error(f"{exc}. You can upload the CSV yourself instead.")
    up = c2.file_uploader("Or upload an official NSE/BSE listing CSV", type=["csv"], key="uni_up")
    ex = c2.selectbox("Exchange of this file", ["NSE", "BSE"], key="uni_ex")
    if up is not None and c2.button("Import file", key="uni_import"):
        with session_scope(f) as s:
            st.success(universe.import_csv(s, up.getvalue(), ex, f"uploaded file {up.name}"))
    st.markdown("**Scan cycle (resumable batches)**")
    cov = scanner.coverage_summary(factory=f)
    st.write(cov["text"] if cov else "No scan cycle has been started.")
    if st.button("Run one scan batch now", key="scan_batch", disabled=cnt["to_scan"] == 0):
        with st.spinner("Scanning a batch..."):
            try:
                cid = cov["cycle_id"] if cov and cov["status"] != "complete" else scanner.start_cycle(f)
                st.write(scanner.run_batch(cid, C.get_provider(), settings_store.get_int("batch_size", f), settings_store.get_int("time_budget_min", f) * 60, None, f))
            except Exception as exc:
                st.error(f"Scan failed: {type(exc).__name__}: {exc}")
    if cov:
        with session_scope(f) as s:
            C.table(C.orm_rows(s.query(ScanItem).filter_by(cycle_id=cov["cycle_id"]).order_by(ScanItem.id).limit(500)))
    st.markdown("**Watchlist (always deep-researched when the universe is empty)**")
    w1, w2, w3 = st.columns([3, 1, 1])
    sym = w1.text_input("Symbol (NSE ticker or BSE scrip code)", key="wl_sym")
    wex = w2.selectbox("Exchange", ["NSE", "BSE"], key="wl_ex")
    if w3.button("Add", key="wl_add", disabled=not sym.strip()):
        try:
            with session_scope(f) as s:
                watchlist.add(s, sym, wex)
        except ValueError as exc:
            st.error(str(exc))
    with session_scope(f) as s:
        C.table(watchlist.entries(s))


# ------------------------------------------------------------------ Floor 02
def _history(symbol, exchange):
    try:
        return C.get_provider().fetch_history(symbol, exchange, period="2y")
    except Exception:
        return None


def _cards(sc, hz):
    items = [("Fundamental /100", (sc["fundamental"] or {}).get("score")), ("Technical /100", (sc["technical"] or {}).get("score")),
             ("Data confidence /100", (sc["data_confidence"] or {}).get("score")), ("Risk /100 (higher = riskier)", (sc["risk"] or {}).get("score")),
             ("Long-term", hz.get("long_term")), ("Short-term", hz.get("short_term")), ("Balanced", hz.get("balanced"))]
    for col, (lab, v) in zip(st.columns(7), items):
        col.markdown(f"<div class='card'>{lab}<br><b>{'n/a' if v is None else v}</b></div>", unsafe_allow_html=True)


def floor02():
    f = C.factory()
    st.subheader("Floor 02 · AI Analyst")
    c1, c2, c3 = st.columns([3, 1, 1])
    sym = c1.text_input("Symbol (e.g. RELIANCE, TCS; BSE scrip code like 500325)", key="sym").strip()
    ex = c2.selectbox("Exchange", ["NSE", "BSE"], key="ex")
    if c3.button("Run research", key="run_analysis", type="primary", disabled=not sym):
        from data.connectors.base import ProviderError
        from data.validation import validate_symbol
        from engine.pipeline import deep_research
        try:
            s_ = validate_symbol(sym)
            with st.spinner("Running 8 agents, then Floors 03 and 07..."):
                out = deep_research(ex, s_, C.get_provider(), C.get_news(), f)
            st.session_state["analysis"] = {"out": out, "symbol": s_, "exchange": ex, "history": _history(s_, ex) if out["coverage"] != "unavailable" else None}
        except ValueError as exc:
            st.error(f"Invalid input: {exc}")
        except ProviderError as exc:
            st.session_state.pop("analysis", None)
            st.error(f"Data provider failed: {exc}. Nothing was estimated. Try again later; the daily pipeline also retries failed stocks.")
    an = st.session_state.get("analysis")
    if not an:
        st.info("Enter an NSE/BSE symbol and choose Run research. Research output is a hypothesis, never advice.")
        return
    r = an["out"]["result"]
    for w in r["warnings"]:
        C.banner(w, "crit" if any(x in w for x in ("CRITICAL", "FAILED", "failed")) else "warn")
    st.markdown("**Agent execution**")
    C.table([{"agent": n, "status": a["status"].upper(), "seconds": a["duration_s"], "missing items": len(a["missing"]), "error": a["error"]} for n, a in r["agents"].items()])
    if not r["scores"]:
        st.error("No scores were produced (see warnings). Missing data stays missing.")
        return
    sc, hz = r["scores"], r["horizon_scores"]
    _cards(sc, hz)
    st.markdown(f"**Risk class:** {sc['risk']['class']}  |  **Tags:** " + (", ".join(t["tag"] for t in r["tags"]) or "none"))
    A = {n: a["data"] for n, a in r["agents"].items()}
    tabs = st.tabs(["Chart", "Fundamental", "Technical", "Business", "Valuation", "News", "Score detail", "Report"])
    with tabs[0]:
        h = an["history"]
        if h is None or len(h) == 0:
            st.warning("Price history could not be re-fetched for the chart.")
        else:
            h = h.tail(400)
            fig = go.Figure(go.Candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close, name="Price", increasing_line_color="#2dd4a0", decreasing_line_color="#ff6b6b"))
            for n, colr in ((20, "#f5c542"), (50, "#6ea8ff"), (200, "#c792ea")):
                fig.add_trace(go.Scatter(x=h.index, y=ta.ema(an["history"]["Close"], n).reindex(h.index), name=f"EMA{n}", line=dict(width=1.2, color=colr)))
            fig.update_layout(template="plotly_dark", paper_bgcolor="#0a1424", plot_bgcolor="#0a1424", height=500, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig)
            st.caption(DELAY + f"Last bar {h.index[-1].date()}.")
        t = A.get("technical") or {}
        if t.get("levels", {}).get("invalidation"):
            st.caption(f"Invalidation level {t['levels']['invalidation']:.2f} (ATR risk distance {C.fmt(t['levels'].get('atr_risk_pct'), 'pct')}). {t['levels']['note']}")
    with tabs[1]:
        fu = A.get("fundamental") or {}
        C.kv(fu.get("metrics", {}))
        st.write("Red flags:", fu.get("red_flags") or "none detected")
        with st.expander("Missing / not computable"):
            st.write(r["agents"]["fundamental"]["missing"])
    with tabs[2]:
        t = A.get("technical") or {}
        st.write({"as_of (completed candles)": t.get("as_of"), "trend": t.get("trend"), "provisional_bar": t.get("provisional_bar")})
        C.kv(t.get("daily", {}))
        st.markdown("**Signals**")
        C.kv(t.get("signals", {}))
        st.markdown("**Assessments**")
        st.write(t.get("short_term"), t.get("long_term"), t.get("levels"), t.get("limitations"))
    with tabs[3]:
        b = A.get("business") or {}
        st.write(f"**{b.get('classification')}**. {b.get('basis')}. {b.get('moat')}")
        C.table([{"check": c["check"], "result": {True: "pass", False: "fail", None: "not evaluable"}[c["passed"]], "evidence": c["evidence"]} for c in b.get("checks", [])])
        with st.expander("Evidence not collected"):
            st.write(r["agents"]["business"]["missing"])
    with tabs[4]:
        v = A.get("valuation") or {}
        st.write(f"**{v.get('assessment')}**. {v.get('method')}")
        C.kv(v.get("ratios", {}))
        st.markdown("**Assumptions (every one shown)**")
        C.table([{"assumption": k, "value": str(x)} for k, x in v.get("assumptions", {}).items()])
        if v.get("scenarios"):
            C.table([{"scenario": k, **x} for k, x in v["scenarios"].items()])
        else:
            st.warning(f"No intrinsic value computed: {v.get('reason')}")
        st.caption("Illustrative output from stated assumptions. Not a price target.")
    with tabs[5]:
        n = A.get("news") or {}
        C.table([{k: i.get(k) for k in ("headline", "source", "published_at", "sentiment", "verification_status", "url")} for i in n.get("items", [])])
        for w in r["agents"]["news"]["warnings"]:
            st.caption(w)
        if r["agents"]["news"]["status"] == "failed":
            st.error(r["agents"]["news"]["error"])
    with tabs[6]:
        for k in ("fundamental", "technical", "data_confidence"):
            blk = sc[k]
            if blk:
                st.markdown(f"**{k.replace('_', ' ').title()}: {blk['score']}/{blk['max']}** (assessable {blk['assessable_points']}/100; unassessed items earn 0 points)")
                C.table([{"component": c["name"], "item": p["name"], "points": "unassessed" if p["points"] is None else p["points"], "max": p["max"], "evidence": p["note"]} for c in blk["components"] for p in c["parts"]])
    with tabs[7]:
        if st.button("Generate report files (HTML, JSON, CSV)", key="make_report"):
            from engine import report_generator
            try:
                paths = report_generator.export_all(r)
                with session_scope(f) as s:
                    for fmt, p in paths.items():
                        s.add(ResearchReport(run_id=r["run_id"], symbol=r["symbol"], exchange=r["exchange"], fmt=fmt, path=p))
                r["report_paths"] = paths
            except Exception as exc:
                st.error(f"Report export failed: {exc}")
        for fmt, p in (r.get("report_paths") or {}).items():
            pp = Path(p)
            if pp.exists():
                st.download_button(f"Download {fmt.upper()}", pp.read_bytes(), file_name=pp.name, key=f"dl_{fmt}")


# ------------------------------------------------------------------ Floor 03
def floor03():
    f = C.factory()
    st.subheader("Floor 03 · Risk Manager")
    C.banner("RESEARCH ONLY: sizing and risk/reward below are illustrations from end-of-day data, not instructions.", "sim")
    an = st.session_state.get("analysis")
    if not an or not an["out"]["result"].get("scores"):
        st.info("Run a research on Floor 02 first. Recent stored findings are shown below.")
        with session_scope(f) as s:
            C.table(C.orm_rows(s.query(RiskFinding).order_by(RiskFinding.id.desc()).limit(50)))
        return
    r = an["out"]["result"]
    rk = r["agents"]["risk"]["data"]
    sev = rk["risk_class"]
    C.banner(f"Risk class: <b>{sev}</b> (score {rk['risk_score']}/100, higher = riskier)", "crit" if sev in ("CRITICAL", "HIGH") else "warn" if sev in ("MODERATE", "UNASSESSED") else "sim")
    if sev == "CRITICAL":
        C.banner("A critical risk is present. No score can override it.", "crit")
    C.table(rk["findings"])
    with st.expander("Checks not performed (unknown is not the same as passed)"):
        C.table([{"check": k, "reason": v} for k, v in rk["unassessed_checks"].items()])
    st.markdown("**Trade setup assessment (illustrative)**")
    from engine import risk_manager
    c1, c2, c3, c4 = st.columns(4)
    cap = c1.number_input("Simulated capital (INR)", 10000.0, 1e9, settings_store.get_float("paper_capital", f), key="cap")
    rp = c2.number_input("Risk per trade %", 0.1, 5.0, settings_store.get_float("risk_per_trade_pct", f), key="rp")
    mp = c3.number_input("Max position %", 1.0, 100.0, settings_store.get_float("max_position_pct", f), key="mp")
    ms = c4.number_input("Max sector %", 1.0, 100.0, settings_store.get_float("max_sector_pct", f), key="ms")
    a = risk_manager.assess_trade(r, cap, rp, mp, ms, 0.0)
    st.write(f"**Verdict: {a['verdict']}** ({a['label']})")
    C.kv({k: a.get(k) for k in ("entry", "stop", "target", "target_basis", "risk_reward", "qty", "position_value", "risk_amount", "risk_per_share") if k in a})
    C.table(a.get("checks", []))
    st.session_state["assessment"] = a


# ------------------------------------------------------------------ Floor 04
def floor04():
    f = C.factory()
    st.subheader("Floor 04 · Paper Executor")
    C.banner("SIMULATED. No broker is connected and no real order is ever placed. Fills use the last known end-of-day close plus slippage.", "sim")
    from engine import paper_broker
    an, a = st.session_state.get("analysis"), st.session_state.get("assessment")
    d = {}
    if an and an["out"]["result"]["agents"]["stock_scout"]["status"] in ("ok", "partial"):
        d = an["out"]["result"]["agents"]["stock_scout"]["data"]
    with st.form("paper_order"):
        c = st.columns(5)
        sym = c[0].text_input("Symbol", an["symbol"] if an else "")
        ex = c[1].selectbox("Exchange", ["NSE", "BSE"], index=0 if not an or an["exchange"] == "NSE" else 1)
        side = c[2].selectbox("Side", ["BUY", "SELL"])
        qty = c[3].number_input("Quantity", 0, 10_000_000, int((a or {}).get("qty") or 0))
        px = c[4].number_input("Reference price (last close)", 0.0, 1e9, float(d.get("last_price") or 0.0))
        c2 = st.columns(2)
        stop = c2[0].number_input("Stop-loss (0 = none)", 0.0, 1e9, float((a or {}).get("stop") or 0.0))
        tgt = c2[1].number_input("Target (0 = none)", 0.0, 1e9, float((a or {}).get("target") or 0.0))
        if st.form_submit_button("Place SIMULATED order"):
            with session_scope(f) as s:
                paper_broker.place_order(s, sym.strip().upper(), ex, side, int(qty), px or None, d.get("last_price_date"), stop or None, tgt or None, d.get("sector"),
                                         settings_store.get_float("slippage_pct", f), f)
            st.success("Order processed. See history below (rejections are recorded with their reason).")
    if st.button("Check stop-loss / target exits now", key="check_exits"):
        with session_scope(f) as s:
            closed = paper_broker.check_exits(s, lambda sy, e: C.get_provider().fetch_history(sy, e, period="3mo"), f)
        st.write(closed or "No simulated exits triggered.")
    with session_scope(f) as s:
        st.markdown("**Open simulated positions**")
        C.table(C.orm_rows(s.query(PaperPosition).filter_by(status="OPEN")))
        st.markdown("**Order history (SIMULATED)**")
        C.table(C.orm_rows(s.query(PaperOrder).order_by(PaperOrder.id.desc()).limit(100)))
        st.markdown("**Closed trades (SIMULATED)**")
        C.table(C.orm_rows(s.query(PaperPosition).filter(PaperPosition.status != "OPEN").order_by(PaperPosition.id.desc()).limit(100)))


# ------------------------------------------------------------------ Floor 05
def floor05():
    f = C.factory()
    st.subheader("Floor 05 · Monitor & Alerts")
    C.banner("Checks run on end-of-day (delayed) data when the pipeline runs, not live. Exchange announcement monitoring is not built yet; news alerts come from unverified headlines.")
    st.markdown("**Open alerts**")
    with session_scope(f) as s:
        al = monitor.open_alerts(s)
    C.table(al)
    if al:
        pick = st.selectbox("Acknowledge alert", [a["id"] for a in al], format_func=lambda i: next(f"#{a['id']} {a['symbol']} {a['kind']}" for a in al if a["id"] == i), key="ack_pick")
        if st.button("Acknowledge", key="ack"):
            with session_scope(f) as s:
                s.get(Alert, pick).acknowledged = True
            st.rerun()
    st.markdown("**Price rules** (checked against the last daily close)")
    c = st.columns(5)
    sym, ex = c[0].text_input("Symbol", key="pr_sym"), c[1].selectbox("Exchange", ["NSE", "BSE"], key="pr_ex")
    dr, px = c[2].selectbox("Direction", ["above", "below"], key="pr_dir"), c[3].number_input("Price", 0.0, 1e9, 0.0, key="pr_px")
    if c[4].button("Add rule", key="pr_add", disabled=not sym.strip() or px <= 0):
        from data.validation import validate_exchange, validate_symbol
        try:
            with session_scope(f) as s:
                s.add(PriceAlertRule(symbol=validate_symbol(sym), exchange=validate_exchange(ex), direction=dr, price=float(px)))
        except ValueError as exc:
            st.error(str(exc))
    if st.button("Check price rules now", key="pr_check"):
        with session_scope(f) as s:
            st.write(f"{len(monitor.check_price_rules(s, C.get_provider()))} rule(s) fired.")
    with session_scope(f) as s:
        C.table(C.orm_rows(s.query(PriceAlertRule).order_by(PriceAlertRule.id.desc())))
        st.markdown("**Watchlist**")
        C.table(watchlist.entries(s))


# ------------------------------------------------------------------ Floor 06
def floor06():
    f = C.factory()
    st.subheader("Floor 06 · Portfolio Manager")
    C.banner("SIMULATED paper portfolio. Not connected to any broker or real account.", "sim")
    refresh = st.button("Refresh prices from provider", key="pf_refresh")
    with session_scope(f) as s:
        sm = portfolio.summary(s, C.get_provider() if refresh else None, f)
    cols = st.columns(5)
    for col, (lab, v, k) in zip(cols, [("Equity", sm["equity"], "num"), ("Cash", sm["cash"], "num"), ("Total return", sm["total_return"], "pct"),
                                       ("Realized P&L", sm["realized_pnl"], "num"), ("Unrealized P&L", sm["unrealized_pnl"], "num")]):
        col.markdown(f"<div class='card'>{lab}<br><b>{C.fmt(v, k)}</b></div>", unsafe_allow_html=True)
    C.table(sm["holdings"])
    if sm["sector_exposure_pct"]:
        st.plotly_chart(go.Figure(go.Bar(x=list(sm["sector_exposure_pct"]), y=list(sm["sector_exposure_pct"].values()), marker_color="#6ea8ff")).update_layout(
            template="plotly_dark", paper_bgcolor="#0a1424", plot_bgcolor="#0a1424", height=300, yaxis_title="% of equity", title="Sector exposure"))
        st.caption(f"Largest single position: {sm['largest_position_pct']:.1f}% of equity.")
    if st.button("Take portfolio snapshot now", key="pf_snap"):
        with session_scope(f) as s:
            portfolio.snapshot(s, None, f)
    with session_scope(f) as s:
        perf = portfolio.performance(s)
    if len(perf["points"]) >= 2:
        st.plotly_chart(go.Figure(go.Scatter(x=[p[0] for p in perf["points"]], y=[p[1] for p in perf["points"]], line=dict(color="#2dd4a0"))).update_layout(
            template="plotly_dark", paper_bgcolor="#0a1424", plot_bgcolor="#0a1424", height=300, title="Equity curve (snapshots)"))
        st.write(f"Max drawdown: {C.fmt(perf['max_drawdown'], 'pct')}")
    else:
        st.caption(perf["note"])


# ------------------------------------------------------------------ Floor 07
def floor07():
    f = C.factory()
    st.subheader("Floor 07 · Final Decision Engine")
    from engine import decision_engine
    st.caption("APPROVE only means worth paper-trading or deeper study. Thresholds: " + ", ".join(f"{k}={v}" for k, v in decision_engine.THRESH.items()))
    with session_scope(f) as s:
        seen, rows = set(), []
        for d in s.query(Decision).order_by(Decision.id.desc()):
            if (d.symbol, d.exchange) in seen:
                continue
            seen.add((d.symbol, d.exchange))
            rows.append(C.orm_rows([d])[0])
    if not rows:
        st.info("No decisions yet. Run research on Floor 02 or run the pipeline on Floor 00.")
        return
    rows.sort(key=lambda x: (x.get("balanced") is None, -(x.get("balanced") or 0)))
    for i, x in enumerate(rows, 1):
        x["rank"] = i
        x["critical_flag"] = "CRITICAL RISK" if x.get("risk_class") == "CRITICAL" else ""
    show = ["rank", "symbol", "exchange", "verdict", "balanced", "fundamental", "technical", "data_confidence", "risk", "risk_class", "critical_flag"]
    C.table([{k: x.get(k) for k in show} for x in rows])
    st.caption("Ranking uses the balanced score = 50% long-term (70% fundamental + 30% technical) + 50% short-term (70% technical + 30% fundamental). Critical risk stays flagged whatever the score.")
    pick = st.selectbox("Explain a decision", [f"{x['exchange']}:{x['symbol']}" for x in rows], key="dec_pick")
    x = next(r for r in rows if f"{r['exchange']}:{r['symbol']}" == pick)
    C.banner(f"<b>{x['verdict']}</b>: " + " | ".join(x.get("reasons") or []), "crit" if x["verdict"] == "REJECT" else "warn" if x["verdict"] == "WATCHLIST" else "sim")
    with st.expander("Risk Manager assessment behind this decision"):
        st.json(x.get("risk_assessment") or {})
    with session_scope(f) as s:
        reps = s.query(ResearchReport).filter_by(symbol=x["symbol"], exchange=x["exchange"]).order_by(ResearchReport.id.desc()).limit(3).all()
        for rp in reps:
            p = Path(rp.path)
            if p.exists():
                st.download_button(f"Download saved {rp.fmt.upper()} report", p.read_bytes(), file_name=p.name, key=f"rep{rp.id}")


def _automation_panel(f):
    from database.models import FloorActivity
    from services import automation_agent, notifier
    st.markdown("**Automation agent** (rule-based, no LLM). Checks the data provider, runs the daily pipeline, re-runs once if it fails, "
                "checks data freshness, writes a digest and notifies you.")
    chans = notifier.configured()
    st.caption("Notification channels configured: " + (", ".join(chans) if chans else "none. Set NTFY_TOPIC, TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, SMTP_* or WEBHOOK_URL (see DEPLOY_ONLINE.md)."))
    c1, c2 = st.columns(2)
    if c1.button("Run automation cycle now", key="auto_run", help="Same steps as the scheduled run. Can take a long time on a large universe."):
        with st.spinner("Automation cycle running..."):
            try:
                automation_agent.run_cycle(provider=C.get_provider(), news=C.get_news(), factory=f, probe_delay_s=3)
            except Exception as exc:
                st.error(f"Automation cycle crashed: {type(exc).__name__}: {exc}")
    if c2.button("Send test notification", key="auto_test", disabled=not chans):
        st.write(notifier.send("Test message from Multibagger Scout AI. If you can read this, notifications work."))
    with session_scope(f) as s:
        row = s.query(FloorActivity).filter_by(event="automation_end").order_by(FloorActivity.id.desc()).first()
        last = None if row is None else {"when": row.created_at, "payload": row.payload or {}}
    if last is None:
        st.caption("The automation agent has not run yet.")
        return
    pl = last["payload"]
    (st.error if pl.get("status") in automation_agent.FAIL_STATUSES else st.success)(f"Last automation cycle ({last['when']} UTC): {str(pl.get('status')).upper()}. {pl.get('message') or ''}")
    if pl.get("probe"):
        st.caption(f"Data-provider check: {'answered' if pl['probe'].get('ok') else 'DID NOT ANSWER'} after {pl['probe'].get('attempts')} attempt(s)." + (f" Latest bar {pl['probe'].get('last_bar')}." if pl["probe"].get("last_bar") else ""))
    if pl.get("digest"):
        st.code(automation_agent.digest_text(pl["status"], pl.get("run_id"), pl["digest"]))
    if pl.get("notifications"):
        st.caption("Notifications: " + ", ".join(f"{n['channel']} {'sent' if n['ok'] else 'FAILED'}" for n in pl["notifications"]))
