from config import settings
from database.connection import session_scope
from database.models import AppSetting

DEFAULTS = {"scheduler_enabled": "true", "schedule_time": settings.DAILY_CHECK_TIME, "batch_size": "50", "time_budget_min": "60",
            "deep_top_n": "30", "refresh_universe": "true", "paper_capital": "1000000", "risk_per_trade_pct": "1.0",
            "max_position_pct": "10", "max_sector_pct": "30", "slippage_pct": "0.1"}


def get(key, factory=None):
    with session_scope(factory) as s:
        row = s.get(AppSetting, key)
        return row.value if row else DEFAULTS[key]


def put(key, value, factory=None):
    if key not in DEFAULTS:
        raise KeyError(key)
    with session_scope(factory) as s:
        row = s.get(AppSetting, key)
        if row:
            row.value = str(value)
        else:
            s.add(AppSetting(key=key, value=str(value)))


def get_bool(key, factory=None):
    return get(key, factory).lower() == "true"


def get_int(key, factory=None):
    return int(float(get(key, factory)))


def get_float(key, factory=None):
    return float(get(key, factory))
