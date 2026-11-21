"""AGENT 3 - Technical analysis on COMPLETED candles. A bar still forming today is reported as provisional only."""
from datetime import datetime, time, timedelta, timezone

import pandas as pd

from data.validation import num
from indicators import ta

IST = timezone(timedelta(hours=5, minutes=30))
CLOSE_BUFFER = time(15, 45)  # NSE closes 15:30 IST; allow data to settle


def split_provisional(df, now=None):
    now = now or datetime.now(IST)
    if len(df) and df.index[-1].date() == now.date() and now.weekday() < 5 and now.time() < CLOSE_BUFFER:
        return df.iloc[:-1], df.iloc[-1:]
    return df, df.iloc[0:0]


def resample_completed(df, rule, last_date):
    """Weekly/monthly bars. A period is kept only once its end date has been reached (slightly conservative
    when the period's nominal last day is a market holiday)."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    r = df.resample(rule).agg(agg).dropna(subset=["Close"])
    return r[r.index <= last_date]


def last(s):
    return None if s is None or len(s) == 0 else num(s.iloc[-1])


def frame_metrics(df):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    ind = {f"ema{n}": ta.ema(c, n) for n in (20, 50, 100, 200)}
    ind.update({f"sma{n}": ta.sma(c, n) for n in (20, 50, 100, 200)})
    mc, ad, bb = ta.macd(c), ta.adx(h, l, c), ta.bollinger(c)
    ind.update(rsi14=ta.rsi(c), atr14=ta.atr(h, l, c), vol_sma20=ta.sma(v, 20), rel_volume=ta.relative_volume(v))
    m = {k: last(s) for k, s in ind.items()}
    m.update(close=last(c), macd=last(mc["macd"]), macd_signal=last(mc["signal"]), macd_hist=last(mc["hist"]),
             adx=last(ad["adx"]), plus_di=last(ad["plus_di"]), minus_di=last(ad["minus_di"]),
             bb_upper=last(bb["upper"]), bb_lower=last(bb["lower"]), bb_pct_b=last(bb["pct_b"]), bb_width=last(bb["width"]),
             atr_pct=(last(ind["atr14"]) / last(c)) if last(ind["atr14"]) and last(c) else None, bars=int(len(df)))
    return m, ind, mc, ad, bb


def classify_trend(m):
    c, e20, e50, e200 = m.get("close"), m.get("ema20"), m.get("ema50"), m.get("ema200")
    if c is None or e20 is None or e50 is None:
        return "Insufficient data"
    if e200 is not None:
        return "Bullish" if c > e50 > e200 else "Bearish" if c < e50 < e200 else "Sideways"
    return "Bullish" if c > e20 > e50 else "Bearish" if c < e20 < e50 else "Sideways"


def run(clean, now=None):
    now = now or datetime.now(IST)
    done, prov = split_provisional(clean, now)
    if len(done) < 30:
        raise ValueError(f"only {len(done)} completed daily bars; need at least 30")
    last_date = done.index[-1]
    dm, ind, mc, ad, bb = frame_metrics(done)
    wk, mo = resample_completed(done, "W-FRI", last_date), resample_completed(done, "ME", last_date)
    wm = frame_metrics(wk)[0] if len(wk) >= 30 else None
    mm = frame_metrics(mo)[0] if len(mo) >= 30 else None
    c, h, l, v = done["Close"], done["High"], done["Low"], done["Volume"]
    atr_v, close = dm["atr14"], dm["close"]

    look = done.iloc[-252:]
    ph, pl = ta.swing_points(look["High"], look["Low"], 5)
    sig = {"higher_high": None, "higher_low": None, "lower_high": None, "lower_low": None}
    if len(ph) >= 2:
        sig["higher_high"], sig["lower_high"] = bool(ph.iloc[-1] > ph.iloc[-2]), bool(ph.iloc[-1] < ph.iloc[-2])
    if len(pl) >= 2:
        sig["higher_low"], sig["lower_low"] = bool(pl.iloc[-1] > pl.iloc[-2]), bool(pl.iloc[-1] < pl.iloc[-2])
    below, above = pl[pl < close], ph[ph > close]
    support, resistance = (num(below.max()) if not below.empty else None), (num(above.min()) if not above.empty else None)

    ph20, pl20 = h.rolling(20).max().shift(1), l.rolling(20).min().shift(1)
    broke = c > ph20
    brk_level = num(ph20.iloc[-1])
    relv = dm["rel_volume"]
    breakout_confirmed = bool(broke.iloc[-1]) and relv is not None and relv >= 1.2
    breakdown = bool(pd.notna(pl20.iloc[-1]) and c.iloc[-1] < pl20.iloc[-1])
    near_breakout = bool(brk_level and not broke.iloc[-1] and (brk_level - close) / brk_level <= 0.03)
    retest = failed_breakout = False
    recent = broke.iloc[-11:-1]
    if not broke.iloc[-1] and recent.any() and atr_v:
        lvl = num(ph20.loc[recent[recent].index[-1]])
        retest = bool(lvl is not None and lvl - 0.5 * atr_v <= close <= lvl + atr_v)
        failed_breakout = bool(lvl is not None and close < lvl - 0.5 * atr_v)
    w = dm["bb_width"]
    bw = bb["width"].iloc[-120:].dropna()
    consolidation = bool(w is not None and len(bw) >= 60 and (bw <= w).mean() <= 0.2 and (dm["adx"] or 99) < 20)
    divergence = None
    r = ind["rsi14"]
    if len(ph) >= 2 and pd.notna(r.get(ph.index[-1])) and pd.notna(r.get(ph.index[-2])) and ph.iloc[-1] > ph.iloc[-2] and r[ph.index[-1]] < r[ph.index[-2]]:
        divergence = "bearish"
    elif len(pl) >= 2 and pd.notna(r.get(pl.index[-1])) and pd.notna(r.get(pl.index[-2])) and pl.iloc[-1] < pl.iloc[-2] and r[pl.index[-1]] > r[pl.index[-2]]:
        divergence = "bullish"
    t21 = done.tail(21)
    up_v = t21["Volume"][t21["Close"].diff() > 0].mean()
    dn_v = t21["Volume"][t21["Close"].diff() < 0].mean()
    s200 = ind["sma200"]
    slope = (s200.iloc[-1] / s200.iloc[-21] - 1) if len(s200) > 21 and pd.notna(s200.iloc[-1]) and pd.notna(s200.iloc[-21]) else None
    order = lambda a, b: None if dm[a] is None or dm[b] is None else bool(dm[a] > dm[b])
    signals = {**sig, "ema_order": {"20>50": order("ema20", "ema50"), "50>100": order("ema50", "ema100"), "100>200": order("ema100", "ema200")},
               "support": support, "resistance": resistance, "prior_20d_high": brk_level,
               "breakout_confirmed": breakout_confirmed, "breakdown": breakdown, "near_breakout": near_breakout,
               "retest_of_breakout": retest, "failed_breakout": failed_breakout, "consolidation": consolidation,
               "rsi_divergence": divergence, "updown_volume_ratio_20d": num(up_v / dn_v) if pd.notna(up_v) and pd.notna(dn_v) and dn_v > 0 else None,
               "sma200_slope_20d": num(slope), "volatility_ann": num(c.pct_change().iloc[-252:].std() * (252 ** 0.5))}

    trend = {"daily": classify_trend(dm), "weekly": classify_trend(wm) if wm else "Insufficient data",
             "monthly": classify_trend(mm) if mm else "Insufficient data"}
    levels = {"note": "Research levels for context, not trade instructions.", "entry_zone": None, "invalidation": None,
              "atr_risk_distance": None, "atr_risk_pct": None}
    if atr_v:
        inv = support - 0.5 * atr_v if support is not None and close - support <= 3 * atr_v else close - 2 * atr_v
        levels.update(invalidation=num(inv), atr_risk_distance=num(close - inv), atr_risk_pct=num((close - inv) / close))
        if trend["daily"] == "Bullish" and dm["ema20"]:
            lo = max(dm["ema20"] - 0.5 * atr_v, support) if support is not None else dm["ema20"] - 0.5 * atr_v
            levels["entry_zone"] = [num(lo), num(dm["ema20"] + 0.5 * atr_v)]
        else:
            levels["entry_zone_note"] = "No entry zone: daily trend is not Bullish"

    def notes_short():
        out = [f"Daily trend {trend['daily']}"]
        if dm["rsi14"] is not None:
            out.append(f"RSI14 {dm['rsi14']:.1f}")
        if dm["macd_hist"] is not None:
            out.append("MACD histogram " + ("positive" if dm["macd_hist"] > 0 else "negative"))
        if breakout_confirmed:
            out.append("confirmed breakout on completed candle")
        if breakdown:
            out.append("breakdown below prior 20-day low")
        return out

    missing = [f"{k}: insufficient history" for k in ("ema200", "sma200") if dm.get(k) is None]
    if wm is None:
        missing.append("weekly indicators: fewer than 30 completed weekly bars")
    if mm is None:
        missing.append("monthly indicators: fewer than 30 completed monthly bars")
    return {"data": {
        "as_of": last_date.date().isoformat(),
        "provisional_bar": None if prov.empty else {"date": prov.index[-1].date().isoformat(), "close": float(prov["Close"].iloc[-1]),
                                                    "label": "PROVISIONAL (session not closed); excluded from all signals"},
        "daily": dm, "weekly": wm, "monthly": mm, "signals": signals, "trend": trend, "levels": levels,
        "short_term": {"assessment": trend["daily"], "basis": notes_short()},
        "long_term": {"assessment": trend["weekly"] if trend["weekly"] != "Insufficient data" else trend["daily"],
                      "basis": [f"Weekly {trend['weekly']}", f"Monthly {trend['monthly']}",
                                "Price " + ("above" if dm["sma200"] and close > dm["sma200"] else "below/unknown vs") + " SMA200"]},
        "limitations": ["4h/1h data not available from this provider; VWAP not computed on daily bars."]},
        "missing": missing, "warnings": []}
