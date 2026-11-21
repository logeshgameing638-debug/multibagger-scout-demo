"""Shared Streamlit helpers. Provider/news getters are indirections so tests can swap in synthetic sources."""
import json

import pandas as pd
import streamlit as st
from sqlalchemy import inspect

from config.logging_setup import setup_logging
from database.connection import init_db

CSS = """<style>
.block-container{max-width:1280px;padding-top:1.2rem}
.card{background:#101e36;border:1px solid #22365a;border-radius:6px;padding:10px 14px;margin-bottom:6px}
.card b{font-size:1.5rem}.warn{background:#3b2d08;border-left:4px solid #f5c542;padding:8px 12px;margin:6px 0}
.crit{background:#3a1015;border-left:4px solid #ff6b6b;padding:8px 12px;margin:6px 0}
.sim{background:#2d1b3d;border-left:4px solid #b07cf0;padding:8px 12px;margin:6px 0;font-weight:600}
.ok{color:#2dd4a0}.bad{color:#ff6b6b}.dim{color:#8fa3c7;font-size:.85rem}
</style>"""


@st.cache_resource
def factory():
    setup_logging()
    return init_db()


def get_provider():
    from data.connectors.yahoo import YahooConnector
    return YahooConnector()


def get_news():
    from data.connectors.rss_news import RssNewsConnector
    return RssNewsConnector()


@st.cache_resource
def scheduler():
    from services.scheduler import start_if_enabled
    return start_if_enabled(factory())


def banner(text, kind="warn"):
    st.markdown(f"<div class='{kind}'>{text}</div>", unsafe_allow_html=True)


def cell(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return v


def table(rows, **kw):
    df = pd.DataFrame(rows)
    if df.empty:
        st.caption("Nothing recorded yet.")
        return
    st.dataframe(df.map(cell) if hasattr(df, "map") else df.applymap(cell), hide_index=True, **kw)


def orm_rows(objs):
    objs = list(objs)
    if not objs:
        return []
    cols = [c.key for c in inspect(type(objs[0])).mapper.column_attrs]
    return [{c: getattr(o, c) for c in cols} for o in objs]


def fmt(v, kind="num"):
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:.1%}" if kind == "pct" else f"{v:,.2f}"
    return str(v)


def kv(d, pct_hint=("growth", "cagr", "roe", "roce", "margin", "conversion", "holding", "yield", "pct")):
    rows = [{"item": k, "value": fmt(v, "pct" if any(h in k for h in pct_hint) else "num")} for k, v in d.items() if not isinstance(v, (dict, list))]
    table(rows)
