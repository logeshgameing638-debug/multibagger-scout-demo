"""AGENT 5 - Valuation. Every assumption is printed; models are illustrative, never price targets."""
from config import settings
from data.validation import num


def _pos(x):
    v = num(x)
    return v if v is not None and v > 0 else None


def _dcf(fcf0, g, r, tg, years=5):
    pv, f = 0.0, fcf0
    for t in range(1, years + 1):
        f *= 1 + g
        pv += f / (1 + r) ** t
    return pv + (f * (1 + tg) / (r - tg)) / (1 + r) ** years


def run(info, price, fund):
    info = info or {}
    m, hist = fund.get("metrics", {}), fund.get("history", {})
    fin = fund.get("is_financial", info.get("sector") == "Financial Services")
    r, tg = settings.DCF_DISCOUNT_RATE, settings.DCF_TERMINAL_GROWTH
    div_rate = _pos(info.get("dividendRate"))
    ratios = {"pe": _pos(info.get("trailingPE")), "forward_pe": _pos(info.get("forwardPE")), "pb": _pos(info.get("priceToBook")),
              "ev_ebitda": _pos(info.get("enterpriseToEbitda")), "ev_sales": _pos(info.get("enterpriseToRevenue")),
              "peg": _pos(info.get("trailingPegRatio") or info.get("pegRatio")),
              "dividend_yield": (div_rate / price) if div_rate and price else None}
    shares = _pos(info.get("sharesOutstanding")) or _pos(info.get("impliedSharesOutstanding"))
    out = {"ratios": ratios, "method": None, "assumptions": {"discount_rate": r, "terminal_growth": tg}, "scenarios": None,
           "margin_of_safety": None, "assessment": "Not assessable", "reason": None, "price": price}

    if fin:  # banks/NBFCs: justified P/B from ROE, not a DCF on cash flows
        roe, bvps = m.get("roe"), _pos(info.get("bookValue"))
        out["method"] = "Justified P/B = (ROE - g) / (r - g), applied to book value per share (financial institution)"
        if roe is None or bvps is None or r <= tg:
            out["reason"] = "ROE or book value per share unavailable"
        else:
            sc = {}
            for name, adj in (("bear", -0.03), ("base", 0.0), ("bull", 0.02)):
                e = min(roe + adj, 0.25)
                jpb = (e - tg) / (r - tg)
                sc[name] = {"roe": e, "justified_pb": jpb, "value_per_share": jpb * bvps if jpb > 0 else None}
            out["scenarios"] = sc
            out["assumptions"].update(roe_scenarios="bear -3pts, base as reported, bull +2pts (capped at 25%)", book_value_per_share=bvps)
    else:
        fcfs = [v for v in hist.get("free_cash_flow", {}).values() if v is not None][:3]
        growth = m.get("sales_cagr_3y") if m.get("sales_cagr_3y") is not None else m.get("sales_growth_1y")
        out["method"] = "2-stage DCF on free cash flow (equity basis), 5-year projection + Gordon terminal value"
        if len(fcfs) < 2 or sum(fcfs) / len(fcfs) <= 0:
            out["reason"] = "needs >=2 years of free cash flow with positive average"
        elif growth is None or shares is None or r <= tg:
            out["reason"] = "needs a sales growth figure and shares outstanding"
        else:
            base_g, start = min(max(growth, 0.0), 0.15), sum(fcfs) / len(fcfs)
            sc = {}
            for name, g in (("bear", base_g * 0.5), ("base", base_g), ("bull", min(base_g * 1.5, 0.20))):
                sc[name] = {"growth": g, "value_per_share": _dcf(start, g, r, tg) / shares}
            out["scenarios"] = sc
            out["assumptions"].update(starting_fcf=start, starting_fcf_basis=f"average of last {len(fcfs)} fiscal years",
                                      base_growth=f"sales growth {growth:.1%}, clamped to 0-15%", bear_growth="50% of base", bull_growth="150% of base (max 20%)",
                                      projection_years=5, shares_outstanding=shares)
    base = (out["scenarios"] or {}).get("base", {}).get("value_per_share")
    if base and base > 0 and price:
        out["margin_of_safety"] = (base - price) / base
        mos = out["margin_of_safety"]
        out["assessment"] = "Attractive" if mos >= 0.25 else "Fair" if mos >= -0.10 else "Expensive"
        out["reason"] = "Margin of safety = (base value - price) / base value"
    elif ratios["peg"] is not None:
        out["assessment"] = "Attractive" if ratios["peg"] < 1 else "Fair" if ratios["peg"] <= 2 else "Expensive"
        out["method"] = (out["method"] or "") + " | fallback: PEG only (no intrinsic value computed)"
    missing = ["industry P/E", "peer valuation", "historical valuation band (need peer/history connectors; not built)"]
    missing += [f"{k}: not provided/meaningful" for k, v in ratios.items() if v is None and k != "dividend_yield"]
    if out["scenarios"] is None:
        missing.append(f"intrinsic value: {out['reason']}")
    return {"data": out, "missing": missing, "warnings": ["Illustrative model output from stated assumptions; not a price target or advice."]}
