"""Multibagger Scout AI: eight-floor research building. Research only: no broker, no real orders; Floor 04 is simulated."""
import hmac
import os

import streamlit as st

st.set_page_config(page_title="Multibagger Scout AI", layout="wide")

for _k in ("DATABASE_URL", "APP_PASSWORD", "NSE_EQUITY_LIST_URL", "EXPORT_DIR", "NTFY_TOPIC", "NTFY_SERVER", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
           "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO", "WEBHOOK_URL"):  # hosted secrets -> environment, before settings load
    if _k not in os.environ:
        try:
            if _k in st.secrets:
                os.environ[_k] = str(st.secrets[_k])
        except Exception:
            pass

from frontend import building, common as C, floors  # noqa: E402

st.markdown(C.CSS, unsafe_allow_html=True)
_pw = os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("auth_ok"):  # basic access gate for a public website; set APP_PASSWORD to enable
    st.title("Multibagger Scout AI")
    _entered = st.text_input("Access password", type="password", key="pw")
    if _entered:
        if hmac.compare_digest(_entered.encode(), _pw.encode()):
            st.session_state["auth_ok"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()
C.factory()
C.scheduler()

FLOORS = {0: ("Central Command", floors.floor00), 1: ("Market Scanner", floors.floor01), 2: ("AI Analyst", floors.floor02), 3: ("Risk Manager", floors.floor03),
          4: ("Paper Executor (SIMULATED)", floors.floor04), 5: ("Monitor & Alerts", floors.floor05), 6: ("Portfolio Manager", floors.floor06),
          7: ("Final Decision Engine", floors.floor07)}
NAV = ["Building overview"] + [f"Floor {i:02d} · {n}" for i, (n, _) in FLOORS.items()]
st.session_state.setdefault("nav", NAV[0])


def go(name):
    st.session_state["nav"] = name


with st.sidebar:
    st.title("Multibagger Scout AI")
    st.radio("Floors", NAV, key="nav")
    st.caption("Research assistant for NSE/BSE stocks. Outputs are research hypotheses, never advice or guaranteed returns. No broker is connected; Floor 04 is simulated.")
    st.caption("Data: Yahoo Finance via yfinance (unofficial, end-of-day or delayed) and public RSS headlines (unverified).")

page = st.session_state["nav"]
if page == NAV[0]:
    building.render(go, lambda i: NAV[i + 1])
else:
    FLOORS[NAV.index(page) - 1][1]()
