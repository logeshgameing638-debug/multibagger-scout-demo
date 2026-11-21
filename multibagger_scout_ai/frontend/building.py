"""Clickable building overview. Only hand-offs seen in the last 60 s are animated; nothing is animated for show."""
import streamlit as st

from frontend import common as C
from services import activity

NAMES = activity.FLOORS
ROW = 46


def _svg(active):
    h = ROW * 8 + 10
    rows = "".join(f"<rect x='10' y='{i*ROW+6}' width='250' height='36' rx='6' fill='#101e36' stroke='#22365a'/>"
                   f"<text x='24' y='{i*ROW+29}' fill='#e6edf7' font-size='14' font-family='Segoe UI,sans-serif'>{i:02d} · {NAMES[i]}</text>" for i in range(8))
    links = ""
    for a, b in active:
        ya, yb = a * ROW + 24, b * ROW + 24
        bend = 60 + abs(a - b) * 18
        links += (f"<path d='M260 {ya} C {260+bend} {ya}, {260+bend} {yb}, 260 {yb}' fill='none' stroke='#2dd4a0' stroke-width='2.5' stroke-dasharray='6 6'>"
                  f"<animate attributeName='stroke-dashoffset' from='24' to='0' dur='0.9s' repeatCount='indefinite'/></path>")
    label = "" if active else "<text x='300' y='30' fill='#8fa3c7' font-size='13' font-family='Segoe UI,sans-serif'>No task is running: connections idle</text>"
    return f"<svg viewBox='0 0 420 {h}' width='100%' xmlns='http://www.w3.org/2000/svg'>{rows}{links}{label}</svg>"


def render(go, nav_for_floor):
    f = C.factory()
    st.subheader("Building overview")
    st.caption("Each card shows the floor's latest logged activity. Status is read from the activity log, never assumed.")
    cols = st.columns(4)
    for i in range(8):
        stt = activity.floor_status(i, factory=f)
        col = cols[i % 4]
        cls = {"ACTIVE": "ok", "ERROR": "bad"}.get(stt["state"], "dim")
        col.markdown(f"<div class='card'><b>{i:02d}</b> {NAMES[i]}<br><span class='{cls}'>{stt['state']}</span>"
                     f"<br><span class='dim'>{(stt['last_event'] or 'no events yet')[:70]}</span><br><span class='dim'>errors in 24 h: {stt['errors_24h']}</span></div>", unsafe_allow_html=True)
        col.button(f"Open floor {i:02d}", key=f"open{i}", on_click=go, args=(nav_for_floor(i),))
    st.markdown("**Task connections (last 60 seconds)**")
    active = activity.active_links(60, factory=f)
    try:  # content is built only from constant floor names and integers (no user or external text)
        doc = "<style>body{margin:0;background:transparent}</style>" + _svg(active)
        if hasattr(st, "iframe"):
            st.iframe(doc, height=ROW * 8 + 20)
        else:
            from streamlit.components.v1 import html
            html(doc, height=ROW * 8 + 20)
    except Exception:
        st.write(", ".join(f"Floor {a:02d} → Floor {b:02d}" for a, b in active) or "No active hand-offs.")
