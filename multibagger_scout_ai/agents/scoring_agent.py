"""AGENT 8 - Scoring. Transparent, reproducible. Missing inputs earn 0 points and shrink 'coverage'; never full marks."""
from datetime import date, datetime

SOURCE_POINTS = {"yfinance": 10}  # unofficial single source; an official filing source would score higher


def P(name, mx, pts, note):
    return {"name": name, "max": mx, "points": None if pts is None else round(min(pts, mx), 2), "note": note}


def comp(name, mx, parts):
    assert abs(sum(p["max"] for p in parts) - mx) < 1e-9, f"{name}: part maxima must sum to {mx}"
    got = sum(p["points"] for p in parts if p["points"] is not None)
    able = sum(p["max"] for p in parts if p["points"] is not None)
    return {"name": name, "max": mx, "points": round(got, 2), "assessable": able, "parts": parts}


def hi(v, bands):  # v >= threshold -> fraction
    return next((f for th, f in bands if v >= th), 0.0)


def lo(v, bands):  # v <= threshold -> fraction
    return next((f for th, f in bands if v <= th), 0.0)


def summarize(components):
    pts, able = sum(c["points"] for c in components), sum(c["assessable"] for c in components)
    return {"score": round(pts, 2), "max": 100, "assessable_points": able, "coverage": round(able / 100, 3),
            "normalized_on_assessed": round(pts / able * 100, 1) if able else None, "components": components}


def growth_part(name, mx, c3, y1):
    v, lab = (c3, "3y CAGR") if c3 is not None else (y1, "1y growth")
    if v is None:
        return P(name, mx, None, "no growth figure computable from available data")
    return P(name, mx, mx * hi(v, [(.20, 1), (.12, .8), (.08, .6), (.03, .3), (1e-9, .1)]), f"{lab} {v:.1%}")


def fundamental(f, val):
    m, fin = f.get("metrics", {}), f.get("is_financial", False)
    pct = lambda k: None if m.get(k) is None else m[k]
    fin_note = "financial institution: industrial rules not applied; sector metrics unavailable"
    ocf, cc, fcf = m.get("operating_cash_flow"), m.get("cash_conversion"), m.get("free_cash_flow")
    roe, roce = pct("roe"), pct("roce")
    de, ic, cr = m.get("debt_to_equity"), m.get("interest_coverage"), m.get("current_ratio")
    ass = val.get("assessment") if val else None
    mos = val.get("margin_of_safety") if val else None
    if mos is not None:
        vpart = P("Valuation vs modelled value", 10, 10 * hi(mos, [(.30, 1), (.15, .8), (0, .6), (-.15, .3)]), f"margin of safety {mos:.1%}")
    elif ass in ("Attractive", "Fair", "Expensive"):
        vpart = P("Valuation (PEG fallback)", 10, {"Attractive": 7, "Fair": 4, "Expensive": 0}[ass], f"assessment {ass} via PEG only")
    else:
        vpart = P("Valuation", 10, None, "no valuation model computable")
    parts = [
        comp("Sales and profit growth", 20, [growth_part("Sales growth", 10, m.get("sales_cagr_3y"), m.get("sales_growth_1y")),
                                             growth_part("Profit growth", 10, m.get("profit_cagr_3y"), m.get("profit_growth_1y"))]),
        comp("ROE and ROCE", 15, [
            P("ROE", 8, None if roe is None else 8 * hi(roe, [(.20, 1), (.15, .75), (.10, .5), (.05, .25)]), "n/a" if roe is None else f"ROE {roe:.1%}"),
            P("ROCE", 7, None if roce is None else 7 * hi(roce, [(.20, 1), (.15, .7), (.10, .45), (.05, .15)]), "n/a" if roce is None else f"ROCE {roce:.1%}")]),
        comp("Debt and balance sheet", 15, [
            P("Debt/equity", 7, None if de is None else 7 * lo(de, [(.3, 1), (.7, .7), (1, .45), (2, .15)]), fin_note if fin else "n/a" if de is None else f"D/E {de:.2f}"),
            P("Interest coverage", 5, None if ic is None else 5 * hi(ic, [(8, 1), (4, .6), (2, .2)]), fin_note if fin else "n/a" if ic is None else f"{ic:.1f}x"),
            P("Current ratio", 3, None if cr is None else 3 * hi(cr, [(1.5, 1), (1, .65), (.8, .35)]), fin_note if fin else "n/a" if cr is None else f"{cr:.2f}")]),
        comp("Cash flow", 15, [
            P("Operating cash flow positive", 5, None if ocf is None else (5 if ocf > 0 else 0), fin_note if fin else "n/a" if ocf is None else f"OCF {ocf:,.0f}"),
            P("Cash conversion", 6, None if cc is None else 6 * hi(cc, [(.9, 1), (.6, .65), (.3, .35)]), fin_note if fin else "n/a (needs positive profit and OCF)" if cc is None else f"OCF/NI {cc:.2f}"),
            P("Free cash flow positive", 4, None if fcf is None else (4 if fcf > 0 else 0), fin_note if fin else "n/a" if fcf is None else f"FCF {fcf:,.0f}")]),
        comp("Management and promoter quality", 15, [P("Promoter holding/pledge/governance", 15, None, "data not available (shareholding connector not built)")]),
        comp("Valuation", 10, [vpart]),
        comp("Industry growth", 10, [P("Industry growth", 10, None, "no industry data collected")]),
    ]
    return summarize(parts)


def technical(t):
    d, w, s = t.get("daily", {}), t.get("weekly"), t.get("signals", {})
    close, atr = d.get("close"), d.get("atr14")
    sma200, slope = d.get("sma200"), s.get("sma200_slope_20d")
    eo = s.get("ema_order", {})
    rsi, hist, adx = d.get("rsi14"), d.get("macd_hist"), d.get("adx")
    relv, udv = d.get("rel_volume"), s.get("updown_volume_ratio_20d")
    hh, hl, lh, ll = s.get("higher_high"), s.get("higher_low"), s.get("lower_high"), s.get("lower_low")
    bull_di = None if d.get("plus_di") is None or d.get("minus_di") is None else d["plus_di"] > d["minus_di"]
    ema_pt = lambda k, lab: P(f"EMA {lab}", 5, None if eo.get(k) is None else (5 if eo[k] else 0), "n/a (insufficient history)" if eo.get(k) is None else ("aligned" if eo[k] else "not aligned"))
    if hh is None or hl is None:
        struct = P("HH/HL structure", 10, None, "fewer than 2 confirmed swing points")
    else:
        struct = P("HH/HL structure", 10, 10 if hh and hl else 5 if hh or hl else 0, f"HH={hh} HL={hl} LH={lh} LL={ll}")
    sup, res = s.get("support"), s.get("resistance")
    if atr and close:
        sp = P("Support nearby", 5, 5 if sup is not None and close - sup <= 3 * atr else 2 if sup is not None else 0,
               "no confirmed swing support below price" if sup is None else f"support {sup:.2f} ({(close - sup) / atr:.1f} ATR below)")
        rp = P("Room to resistance", 5, 5 if res is None else 5 if (res - close) / atr >= 2 else 2 if (res - close) / atr >= 1 else 0,
               "no overhead swing resistance in last year" if res is None else f"resistance {res:.2f} ({(res - close) / atr:.1f} ATR above)")
    else:
        sp, rp = P("Support nearby", 5, None, "ATR unavailable"), P("Room to resistance", 5, None, "ATR unavailable")
    if s.get("failed_breakout") or s.get("breakdown"):
        bo = P("Breakout confirmation", 15, 0, "breakdown or failed breakout")
    elif s.get("breakout_confirmed"):
        bo = P("Breakout confirmation", 15, 15, "completed-candle close above prior 20d high on volume >=1.2x")
    elif s.get("retest_of_breakout"):
        bo = P("Breakout confirmation", 15, 10, "retesting a recent breakout level")
    elif s.get("near_breakout"):
        bo = P("Breakout confirmation", 15, 5, "within 3% of prior 20d high, not yet broken")
    else:
        bo = P("Breakout confirmation", 15, 0, "no breakout setup")
    wk_ok = None if not w or w.get("ema50") is None or w.get("close") is None else w["close"] > w["ema50"]
    parts = [
        comp("Long-term trend", 20, [
            P("Price above SMA200", 8, None if sma200 is None or close is None else (8 if close > sma200 else 0), "n/a" if sma200 is None else f"close {close:.2f} vs SMA200 {sma200:.2f}"),
            P("SMA200 rising", 6, None if slope is None else (6 if slope > 0.02 else 3 if slope > 0 else 0), "n/a" if slope is None else f"20-bar slope {slope:.1%}"),
            P("Weekly close above weekly EMA50", 6, None if wk_ok is None else (6 if wk_ok else 0), "n/a (insufficient weekly history)" if wk_ok is None else str(wk_ok))]),
        comp("EMA alignment", 15, [ema_pt("20>50", "20 > 50"), ema_pt("50>100", "50 > 100"), ema_pt("100>200", "100 > 200")]),
        comp("Momentum", 15, [
            P("RSI14", 8, None if rsi is None else 8 if 50 <= rsi <= 70 else 5 if 70 < rsi <= 80 else 3 if 40 <= rsi < 50 else 0, "n/a" if rsi is None else f"RSI {rsi:.1f}"),
            P("MACD histogram", 4, None if hist is None else (4 if hist > 0 else 0), "n/a" if hist is None else f"hist {hist:.3f}"),
            P("ADX trend strength", 3, None if adx is None or bull_di is None else 3 if adx >= 25 and bull_di else 1 if adx >= 20 and bull_di else 0, "n/a" if adx is None else f"ADX {adx:.1f}, +DI>-DI={bull_di}")]),
        comp("Volume", 15, [
            P("Relative volume", 8, None if relv is None else 8 * hi(relv, [(1.5, 1), (1.0, .625), (.7, .25)]), "n/a" if relv is None else f"{relv:.2f}x prior 20-bar average"),
            P("Up/down volume balance", 7, None if udv is None else 7 * hi(udv, [(1.3, 1), (1.0, .57)]), "n/a" if udv is None else f"up-day/down-day volume {udv:.2f}")]),
        comp("Price structure", 10, [struct]),
        comp("Support and resistance", 10, [sp, rp]),
        comp("Breakout confirmation", 15, [bo]),
    ]
    return summarize(parts)


def data_confidence(provider, scout, f, val, info, today):
    m = f.get("metrics", {})
    fin = f.get("is_financial", False)
    skip = {"debt_to_equity", "interest_coverage", "current_ratio", "working_capital", "total_debt", "operating_cash_flow", "free_cash_flow", "cash_conversion"} if fin else set()
    skip |= {"sales_cagr_5y", "profit_cagr_5y", "insider_holding_yahoo"}  # known unavailable from this source; shown as missing elsewhere
    keys = [k for k in m if k not in skip]
    got = sum(m[k] is not None for k in keys)
    rat = [v for v in (val or {}).get("ratios", {}).values()]
    got_r, exp_r = sum(v is not None for v in rat), len(rat)
    comp_frac = (got + got_r) / (len(keys) + exp_r) if keys or exp_r else 0.0
    depth = f.get("annual_periods", 0)
    lp = f.get("latest_annual_period")
    age_m = None if not lp else (today - date.fromisoformat(lp)).days / 30.4
    pdate = scout.get("last_price_date")
    pdays = None if not pdate else (today - date.fromisoformat(pdate)).days
    price_info = info.get("currentPrice") or info.get("regularMarketPrice")
    lastp = scout.get("last_price")
    mc, sh = info.get("marketCap"), info.get("sharesOutstanding")
    pc = None if not price_info or not lastp else abs(price_info - lastp) / lastp <= 0.05
    mcc = None if not (mc and sh and lastp) else abs(mc - lastp * sh) / mc <= 0.10
    parts = [
        comp("Source reliability", 20, [P("Provider reliability", 20, SOURCE_POINTS.get(provider["name"], 0), f"{provider['name']}: unofficial/unknown-reliability provider scores at most 10/20")]),
        comp("Data completeness", 30, [P("Metrics available", 30, 30 * comp_frac, f"{got + got_r} of {len(keys) + exp_r} expected metrics available")]),
        comp("Reporting period", 15, [
            P("History depth", 8, 8 * {5: 1, 4: .75, 3: .5, 2: .25}.get(min(depth, 5), 0), f"{depth} annual periods"),
            P("Latest annual period recency", 7, None if age_m is None else 7 if age_m <= 15 else 3 if age_m <= 24 else 0, "n/a" if age_m is None else f"latest period {lp} ({age_m:.0f} months old)")]),
        comp("Freshness", 20, [P("Last price bar age", 20, None if pdays is None else 20 if pdays <= 3 else 14 if pdays <= 7 else 6 if pdays <= 30 else 0, "n/a" if pdays is None else f"{pdays} days old")]),
        comp("Cross-source consistency", 15, [
            P("Cross-provider agreement", 9, 0, "only one provider connected; cannot cross-check"),
            P("Quoted price vs last close", 3, None if pc is None else (3 if pc else 0), "n/a" if pc is None else f"within 5%: {pc}"),
            P("Market cap vs price x shares", 3, None if mcc is None else (3 if mcc else 0), "n/a" if mcc is None else f"within 10%: {mcc}")]),
    ]
    if provider.get("is_synthetic"):
        parts[0] = comp("Source reliability", 20, [P("Provider reliability", 20, 0, "SYNTHETIC TEST DATA: not real market data")])
    return summarize(parts)


def run(provider, scout, fund, tech, val, risk, info, today=None):
    today = today or datetime.now().date()
    out = {"fundamental": fundamental(fund, val) if fund else None, "technical": technical(tech) if tech else None,
           "data_confidence": data_confidence(provider, scout, fund or {}, val, info or {}, today),
           "risk": {"score": risk.get("risk_score"), "class": risk.get("risk_class"), "scale": "0-100, higher = MORE risk (not a better investment)",
                    "drivers": [f"{x['severity']}: {x['title']}" for x in risk.get("findings", [])]} if risk else None}
    miss = [k for k in ("fundamental", "technical", "risk") if out[k] is None]
    return {"data": out, "missing": [f"{k} score not computed (agent failed or skipped)" for k in miss], "warnings": []}
