"""AGENT 1 - Stock Scout: identity validation and liquidity for one candidate. Never invents a listing."""
from data.validation import num


def run(pr, clean, issues):
    info = pr.info or {}
    name = info.get("longName") or info.get("shortName")
    last = clean.iloc[-1]
    tail = clean.tail(20)
    traded = float((tail["Close"] * tail["Volume"]).mean())
    liquidity = "HIGH" if traded >= 1e8 else "ADEQUATE" if traded >= 1e7 else "LOW"  # INR 10 cr / 1 cr
    missing = []
    for key, label in (("sector", "sector"), ("industry", "industry"), ("marketCap", "market cap")):
        if not info.get(key):
            missing.append(f"{label} (not provided by source)")
    if not name:
        missing.append("company name (not provided by source; identity unverified)")
    warnings = list(issues)
    if len(clean) < 250:
        warnings.append(f"only {len(clean)} daily bars; long-term indicators will be limited")
    return {
        "data": {
            "symbol": pr.symbol, "exchange": pr.exchange, "company_name": name,
            "sector": info.get("sector"), "industry": info.get("industry"), "market_cap": num(info.get("marketCap")),
            "last_price": float(last["Close"]), "last_price_date": clean.index[-1].date().isoformat(),
            "avg_volume_20d": float(tail["Volume"].mean()), "avg_traded_value_20d_inr": traded,
            "liquidity_class": liquidity, "history_bars": int(len(clean)),
            "history_start": clean.index[0].date().isoformat(),
            "availability": {k: (k in pr.statements) for k in ("annual_income", "annual_balance", "annual_cashflow", "quarterly_income")},
            "source": pr.provider, "source_note": pr.note, "fetched_at": pr.fetched_at.isoformat(),
        },
        "missing": missing, "warnings": warnings,
    }
