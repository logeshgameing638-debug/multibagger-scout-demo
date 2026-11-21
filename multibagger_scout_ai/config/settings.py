"""Central configuration. Secrets/overrides come from environment variables or .env (never hardcoded)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv is optional
    pass

ROOT = Path(__file__).resolve().parent.parent


def _env(key, default):
    return os.environ.get(key, default)


DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{(ROOT / 'scout.db').as_posix()}")
if DATABASE_URL.startswith("postgres://"):  # some hosts hand out the short scheme
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]
EXPORT_DIR = Path(_env("EXPORT_DIR", str(ROOT / "exports"))).resolve()
HISTORY_PERIOD = _env("HISTORY_PERIOD", "10y")
HTTP_TIMEOUT = int(_env("HTTP_TIMEOUT", "15"))

# DCF / valuation assumptions (shown in every valuation report)
DCF_DISCOUNT_RATE = float(_env("DCF_DISCOUNT_RATE", "0.12"))
DCF_TERMINAL_GROWTH = float(_env("DCF_TERMINAL_GROWTH", "0.05"))

# News: public RSS search feed. Replace via env if the provider changes or terms do not suit you.
NEWS_FEED_TEMPLATE = _env(
    "NEWS_FEED_TEMPLATE",
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en",
)
NEWS_MAX_ITEMS = int(_env("NEWS_MAX_ITEMS", "25"))

# Daily check agent
DAILY_CHECK_ENABLED = _env("DAILY_CHECK_ENABLED", "true").lower() == "true"
DAILY_CHECK_TIME = _env("DAILY_CHECK_TIME", "18:30")  # local time, HH:MM (after NSE close + data settle)
SCORE_CHANGE_ALERT_POINTS = float(_env("SCORE_CHANGE_ALERT_POINTS", "8"))

# Official NSE list of equity listings (CSV). Not verified from the build environment; if it fails, import the CSV by hand on Floor 01.
NSE_EQUITY_LIST_URL = _env("NSE_EQUITY_LIST_URL", "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")

RATE_LIMIT_PER_MIN = int(_env("RATE_LIMIT_PER_MIN", "30"))
API_KEY = _env("API_KEY", "")  # if set, backend requires header X-API-Key

# Automation agent (services/automation_agent.py)
PROBE_SYMBOL = _env("PROBE_SYMBOL", "RELIANCE")          # liquid stock used only to test that the data provider answers
PROBE_RETRIES = int(_env("PROBE_RETRIES", "2"))
PROBE_DELAY_S = float(_env("PROBE_DELAY_S", "120"))
CYCLE_RETRIES = int(_env("CYCLE_RETRIES", "1"))           # re-run once if the whole pipeline fails
STALE_DAYS = int(_env("STALE_DAYS", "4"))                 # newest stored price older than this = stale (holidays are not modelled)
BUSY_HOURS = float(_env("BUSY_HOURS", "3"))               # a 'running' pipeline newer than this blocks a second start
