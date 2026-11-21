import math
import re

import pandas as pd

SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")
EXCHANGES = ("NSE", "BSE")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def num(x):
    """Return a finite float or None (never raises, never turns missing into 0)."""
    try:
        if x is None or isinstance(x, bool):
            return None
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def validate_symbol(symbol) -> str:
    if not isinstance(symbol, str):
        raise ValueError("symbol must be a string")
    s = symbol.strip().upper()
    for suffix in (".NS", ".BO"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    if not SYMBOL_RE.match(s):
        raise ValueError(f"invalid symbol: {symbol!r}")
    return s


def validate_exchange(exchange) -> str:
    e = str(exchange).strip().upper()
    if e not in EXCHANGES:
        raise ValueError(f"exchange must be one of {EXCHANGES}")
    return e


def clean_ohlcv(df):
    """Validate and clean OHLCV. Returns (clean_df, issues). Raises ValueError if unusable."""
    issues = []
    if df is None or len(df) == 0:
        raise ValueError("no price data")
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV columns missing: {missing}")
    d = df[OHLCV].copy()
    d.index = pd.to_datetime(d.index)
    if d.index.tz is not None:
        d.index = d.index.tz_localize(None)
    d.index = d.index.normalize()
    dup = int(d.index.duplicated(keep="last").sum())
    if dup:
        issues.append(f"removed {dup} duplicate dates")
        d = d[~d.index.duplicated(keep="last")]
    d = d.sort_index()
    bad = d.isna().any(axis=1) | (d[["Open", "High", "Low", "Close"]] <= 0).any(axis=1) | (d["High"] < d["Low"])
    if bad.any():
        issues.append(f"dropped {int(bad.sum())} invalid rows (NaN, non-positive price or High<Low)")
        d = d[~bad]
    if d.empty:
        raise ValueError("no valid price rows after cleaning")
    return d, issues
