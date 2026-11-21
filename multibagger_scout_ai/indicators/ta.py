"""Custom technical indicators (Wilder smoothing where standard). No external TA dependency."""
import numpy as np
import pandas as pd


def sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close, n=14):
    d = close.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + au / ad)
    out = out.where(ad != 0, 100.0)
    return out.mask((au == 0) & (ad == 0), 50.0)


def macd(close, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def true_range(h, l, c):
    pc = c.shift(1)
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def atr(h, l, c, n=14):
    return true_range(h, l, c).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(h, l, c, n=14):
    up, dn = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=h.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=h.index)
    a = 1 / n
    atr_ = true_range(h, l, c).ewm(alpha=a, adjust=False, min_periods=n).mean()
    pdi = 100 * plus_dm.ewm(alpha=a, adjust=False, min_periods=n).mean() / atr_
    mdi = 100 * minus_dm.ewm(alpha=a, adjust=False, min_periods=n).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pd.DataFrame({"adx": dx.ewm(alpha=a, adjust=False, min_periods=n).mean(), "plus_di": pdi, "minus_di": mdi})


def bollinger(close, n=20, k=2.0):
    mid, sd = sma(close, n), close.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    return pd.DataFrame({"mid": mid, "upper": up, "lower": lo, "width": (up - lo) / mid,
                         "pct_b": (close - lo) / (up - lo).replace(0, np.nan)})


def relative_volume(vol, n=20):
    """Volume divided by the average of the PRIOR n bars (current bar excluded)."""
    return vol / vol.rolling(n, min_periods=n).mean().shift(1).replace(0, np.nan)


def swing_points(high, low, window=5):
    """Confirmed pivots: need `window` later bars, so the newest `window` bars can never be pivots."""
    size = 2 * window + 1
    ph = high[high == high.rolling(size, center=True).max()].dropna()
    pl = low[low == low.rolling(size, center=True).min()].dropna()
    return ph, pl
