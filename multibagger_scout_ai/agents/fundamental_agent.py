"""AGENT 2 - Fundamental analysis from reported statements. Ratios are computed only from available inputs."""
from data.validation import num

IS_REV = ["Total Revenue", "Operating Revenue"]
IS_NI = ["Net Income", "Net Income Common Stockholders"]
IS_EBIT = ["EBIT", "Operating Income"]
IS_GP = ["Gross Profit"]
IS_INT = ["Interest Expense", "Interest Expense Non Operating"]
IS_EPS = ["Diluted EPS", "Basic EPS"]
BS_EQ = ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"]
BS_DEBT = ["Total Debt"]
BS_CA, BS_CL, BS_TA = ["Current Assets"], ["Current Liabilities"], ["Total Assets"]
BS_SH = ["Ordinary Shares Number", "Share Issued"]
CF_OCF = ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]
CF_FCF = ["Free Cash Flow"]


def row(df, aliases):
    """Series (latest period first) for the first matching line item, else None."""
    if df is None or getattr(df, "empty", True):
        return None
    for a in aliases:
        if a in df.index:
            s = df.loc[a].dropna()
            if not s.empty:
                return s.sort_index(ascending=False)
    return None


def latest(s):
    return None if s is None or s.empty else num(s.iloc[0])


def cagr(s, years):
    if s is None or len(s) < years + 1:
        return None
    new, old = num(s.iloc[0]), num(s.iloc[years])
    if new is None or old is None or new <= 0 or old <= 0:
        return None
    return (new / old) ** (1 / years) - 1


def yoy(s):
    if s is None or len(s) < 2:
        return None
    new, old = num(s.iloc[0]), num(s.iloc[1])
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old)


def ratio(a, b):
    return None if a is None or b in (None, 0) else a / b


def is_financial(info):
    return (info or {}).get("sector") == "Financial Services"


def run(pr):
    st, info = pr.statements, pr.info or {}
    inc, bal, cf, q = st.get("annual_income"), st.get("annual_balance"), st.get("annual_cashflow"), st.get("quarterly_income")
    fin = is_financial(info)
    rev, ni, ebit, gp = row(inc, IS_REV), row(inc, IS_NI), row(inc, IS_EBIT), row(inc, IS_GP)
    intexp, eps = row(inc, IS_INT), row(inc, IS_EPS)
    eq, debt, ca, cl, ta, sh = (row(bal, x) for x in (BS_EQ, BS_DEBT, BS_CA, BS_CL, BS_TA, BS_SH))
    ocf, fcf = row(cf, CF_OCF), row(cf, CF_FCF)

    equity, ni0, ebit0 = latest(eq), latest(ni), latest(ebit)
    ie = latest(intexp)
    cap_employed = None if latest(ta) is None or latest(cl) is None else latest(ta) - latest(cl)
    m = {
        "sales_growth_1y": yoy(rev), "sales_cagr_3y": cagr(rev, 3), "sales_cagr_5y": cagr(rev, 5),
        "profit_growth_1y": yoy(ni), "profit_cagr_3y": cagr(ni, 3), "profit_cagr_5y": cagr(ni, 5),
        "eps_growth_1y": yoy(eps),
        "roe": ratio(ni0, equity) if equity and equity > 0 else None,
        "roce": ratio(ebit0, cap_employed) if cap_employed and cap_employed > 0 else None,
        "operating_margin": ratio(ebit0, latest(rev)), "net_margin": ratio(ni0, latest(rev)),
        "gross_margin": ratio(latest(gp), latest(rev)),
        "total_debt": latest(debt), "debt_to_equity": ratio(latest(debt), equity) if equity and equity > 0 else None,
        "interest_coverage": ratio(ebit0, abs(ie)) if ie else None,
        "current_ratio": ratio(latest(ca), latest(cl)),
        "working_capital": None if latest(ca) is None or latest(cl) is None else latest(ca) - latest(cl),
        "operating_cash_flow": latest(ocf), "free_cash_flow": latest(fcf),
        "cash_conversion": ratio(latest(ocf), ni0) if ni0 and ni0 > 0 else None,
        "shares_outstanding_growth": None if sh is None or len(sh) < 2 or not num(sh.iloc[-1]) else num(sh.iloc[0]) / num(sh.iloc[-1]) - 1,
        "latest_equity": equity, "latest_net_income": ni0,
        "institutional_holding": num(info.get("heldPercentInstitutions")),
        "insider_holding_yahoo": num(info.get("heldPercentInsiders")),
    }
    if fin:  # industrial leverage/liquidity/cash-flow rules do not apply to banks/NBFCs
        for k in ("debt_to_equity", "interest_coverage", "current_ratio", "working_capital", "total_debt",
                  "operating_cash_flow", "free_cash_flow", "cash_conversion"):
            m[k] = None

    def series(s):
        return {d.date().isoformat() if hasattr(d, "date") else str(d): num(v) for d, v in (s.items() if s is not None else [])}

    history = {"revenue": series(rev), "net_income": series(ni), "operating_income": series(ebit), "operating_cash_flow": series(ocf),
               "free_cash_flow": series(fcf), "equity": series(eq)}
    qrev, qni = row(q, IS_REV), row(q, IS_NI)
    quarterly = {"revenue": series(qrev), "net_income": series(qni),
                 "revenue_yoy_latest_quarter": (num(qrev.iloc[0]) / num(qrev.iloc[4]) - 1) if qrev is not None and len(qrev) >= 5 and num(qrev.iloc[4]) else None}

    reasons = {
        "sales_cagr_5y": "needs 6 annual periods; source gives fewer", "profit_cagr_5y": "needs 6 annual periods; source gives fewer",
    }
    skip = {"debt_to_equity", "interest_coverage", "current_ratio", "working_capital", "total_debt", "operating_cash_flow",
            "free_cash_flow", "cash_conversion"} if fin else set()
    missing = [f"{k}: {reasons.get(k, 'not computable from available data')}" for k, v in m.items() if v is None and k not in skip]
    missing += ["promoter_holding: not in Yahoo data; needs NSE/BSE shareholding-pattern connector (not built)",
                "promoter_holding_change: same", "promoter_pledge: same"]
    if fin:
        missing.append("bank/NBFC metrics (NIM, GNPA, CAR): not available from this source")

    flags = []
    if equity is not None and equity <= 0:
        flags.append("Negative or zero shareholders' equity")
    if latest(ocf) is not None and latest(ocf) < 0 and not fin:
        flags.append("Negative operating cash flow in latest fiscal year")
    if m["sales_growth_1y"] is not None and m["sales_growth_1y"] < 0:
        flags.append("Sales declined year over year")
    if m["interest_coverage"] is not None and m["interest_coverage"] < 1.5:
        flags.append(f"Weak interest coverage ({m['interest_coverage']:.2f}x)")
    periods = int(len(rev)) if rev is not None else 0
    latest_period = rev.index[0].date().isoformat() if rev is not None else None
    if not st:
        raise ValueError("no financial statements available from provider")
    return {"data": {"metrics": m, "history": history, "quarterly": quarterly, "red_flags": flags, "is_financial": fin,
                     "annual_periods": periods, "latest_annual_period": latest_period},
            "missing": missing, "warnings": ["Financial line-item mapping is unverified against live data; check data quality log on first run."]}
