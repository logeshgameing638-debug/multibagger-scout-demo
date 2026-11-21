# LEGACY single-stock page kept for reference. It reads field names the current agents no longer use (e.g. p["label"]); do not run.
"""Streamlit dashboard (slice: single-stock research page). Pages 2-17 of the master spec are NOT built yet."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import orchestrator
from engine.utils import to_jsonable
from indicators import ta

st.set_page_config(page_title="Multibagger Scout AI", layout="wide")
st.markdown("""<style>
.block-container{max-width:1200px;padding-top:1.4rem}
.card{background:#101e36;border:1px solid #22365a;border-radius:6px;padding:10px 14px}
.card b{font-size:1.6rem}.warn{background:#3b2d08;border-left:4px solid #f5c542;padding:8px 12px;margin:6px 0}
.crit{background:#3a1015;border-left:4px solid #ff6b6b;padding:8px 12px;margin:6px 0}
</style>""", unsafe_allow_html=True)

st.title("Multibagger Scout AI")
st.caption("Research assistant for NSE/BSE stocks. Outputs are research hypotheses, not investment advice. No orders are ever placed.")

with st.sidebar:
    st.header("Analyse a stock")
    symbol = st.text_input("Symbol (e.g. RELIANCE, TCS, 500325)", value="").strip()
    exchange = st.selectbox("Exchange", ["NSE", "BSE"])
    run = st.button("Run research", type="primary", disabled=not symbol)
    st.caption("Data: Yahoo Finance via yfinance (unofficial, may be delayed) and public RSS headlines.")

if run:
    with st.spinner("Running 8 agents..."):
        try:
            st.session_state["res"] = orchestrator.analyze(symbol, exchange)
        except ValueError as e:
            st.error(f"Invalid input: {e}")

res = st.session_state.get("res")
if not res:
    st.info("Enter an NSE/BSE symbol in the sidebar and choose Run research.")
    st.stop()

for w in res["warnings"]:
    st.markdown(f"<div class='{'crit' if 'CRITICAL' in w or 'FAILED' in w or 'failed' in w else 'warn'}'>{w}</div>", unsafe_allow_html=True)

st.subheader("Agent execution status")
st.dataframe(pd.DataFrame([{"agent": n, "status": a["status"], "seconds": a["duration_s"], "missing items": len(a["missing"]), "error": a["error"]} for n, a in res["agents"].items()]),
             hide_index=True, use_container_width=True)

sc, hs = res["scores"], res["horizon_scores"]
if not sc:
    st.error("No scores were produced (see warnings above).")
    st.stop()
cols = st.columns(7)
for col, (lab, val) in zip(cols, [("Fundamental /100", sc["fundamental"]), ("Technical /100", sc["technical"]), ("Data confidence /100", sc["data_confidence"]),
                                  ("Risk /100 (higher = riskier)", sc["risk"]), ("Long-term", hs["long_term"]), ("Short-term", hs["short_term"]), ("Balanced", hs["balanced"])]):
    col.markdown(f"<div class='card'>{lab}<br><b>{'n/a' if val is None else val}</b></div>", unsafe_allow_html=True)
st.markdown(f"**Risk class:** {sc['risk_class']}  |  **Tags:** " + (", ".join(t["tag"] for t in res["tags"]) or "none"))

A = {n: a["data"] for n, a in res["agents"].items()}
tabs = st.tabs(["Chart", "Fundamental", "Technical", "Business", "Valuation", "Risk", "News", "Score detail", "Export"])
with tabs[0]:
    h = res["_history"].tail(400)
    close = res["_history"]["Close"]
    fig = go.Figure(go.Candlestick(x=h.index, open=h.Open, high=h.High, low=h.Low, close=h.Close, name="Price",
                                   increasing_line_color="#2dd4a0", decreasing_line_color="#ff6b6b"))
    for n, colr in ((20, "#f5c542"), (50, "#6ea8ff"), (200, "#c792ea")):
        fig.add_trace(go.Scatter(x=h.index, y=ta.ema(close, n).reindex(h.index), name=f"EMA{n}", line=dict(width=1.2, color=colr)))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#0a1424", plot_bgcolor="#0a1424", height=520, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    lv = A["technical"].get("levels", {})
    if lv.get("invalidation_level"):
        st.caption(f"Invalidation level {lv['invalidation_level']:.2f} (risk distance {lv['risk_distance_pct']:.1%}, {lv['risk_distance_atr']:.1f} ATR). {lv['note']}")
with tabs[1]:
    st.json(to_jsonable({"metrics": A["fundamental"].get("metrics"), "red_flags": A["fundamental"].get("red_flags")}))
    st.write("Missing:", res["agents"]["fundamental"]["missing"])
with tabs[2]:
    st.json(to_jsonable({k: A["technical"].get(k) for k in ("as_of", "trend", "short_term", "long_term", "signals", "levels", "notes")}))
with tabs[3]:
    st.json(to_jsonable(A["business"]))
with tabs[4]:
    st.json(to_jsonable(A["valuation"]))
with tabs[5]:
    st.dataframe(pd.DataFrame(A["risk"].get("findings", [])), hide_index=True, use_container_width=True)
    st.write("Unassessed (unknown, NOT passed):", A["risk"].get("unassessed_checks"))
with tabs[6]:
    items = [i for i in A["news"].get("items", []) if i["relevance"] == "High"]
    st.dataframe(pd.DataFrame(items)[["headline", "source", "published_at", "sentiment", "verification_status", "url"]] if items else pd.DataFrame(), hide_index=True, use_container_width=True)
    st.caption(A["news"].get("caveat", ""))
with tabs[7]:
    for k in ("fundamental", "technical", "data_confidence"):
        blk = A["scoring"].get(k)
        if blk:
            st.markdown(f"**{k.replace('_', ' ').title()}: {blk['score']}/{blk['max']}** (coverage {blk['coverage']:.0%})")
            st.dataframe(pd.DataFrame([{"component": c["name"], "part": p["label"], "points": p["points"], "max": p["max"], "note": p["note"]} for c in blk["components"] for p in c["parts"]]),
                         hide_index=True, use_container_width=True)
with tabs[8]:
    for fmt, path in (res.get("report_paths") or {}).items():
        p = Path(path)
        st.download_button(f"Download {fmt.upper()}", p.read_bytes(), file_name=p.name, key=fmt)
