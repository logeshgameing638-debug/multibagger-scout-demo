"""AGENT 6 - Risk analysis. Higher score = MORE risk. Unassessed checks are listed, never silently passed."""
WEIGHT = {"CRITICAL": 35, "HIGH": 20, "MODERATE": 10, "LOW": 3}
UNASSESSED = {
    "promoter_pledge": "needs NSE/BSE shareholding pattern (connector not built)",
    "promoter_selling": "needs NSE/BSE shareholding pattern (connector not built)",
    "auditor_resignation_or_qualified_opinion": "needs official filings (connector not built); headline signals only",
    "related_party_transactions": "needs annual report parsing (not built)",
    "regulatory_issues": "needs SEBI/exchange feeds (not built); headline signals only",
    "concentration_risk": "needs segment/customer data (not available)",
}


def _f(category, severity, title, evidence, as_of, verified=True):
    return {"category": category, "severity": severity, "title": title, "evidence": evidence, "as_of": as_of, "verified": verified}


def run(info, scout, fund, val, news, tech):
    m = fund.get("metrics", {})
    fin = fund.get("is_financial", False)
    fund_date = fund.get("latest_annual_period")
    mkt_date = scout.get("last_price_date")
    findings, assessed = [], set()

    if m and not fin:
        assessed.add("leverage")
        de, ic, ocf, eq = m.get("debt_to_equity"), m.get("interest_coverage"), m.get("operating_cash_flow"), m.get("latest_equity")
        if eq is not None and eq <= 0:
            findings.append(_f("leverage", "CRITICAL", "Negative shareholders' equity", f"Equity {eq:,.0f}", fund_date))
        if ic is not None and ic < 1 and ocf is not None and ocf < 0:
            findings.append(_f("leverage", "CRITICAL", "Debt-servicing distress", f"Interest coverage {ic:.2f}x with negative operating cash flow", fund_date))
        if de is not None and de > 2:
            findings.append(_f("leverage", "HIGH", "High leverage", f"Debt/equity {de:.2f}", fund_date))
        elif de is not None and de > 1:
            findings.append(_f("leverage", "MODERATE", "Elevated leverage", f"Debt/equity {de:.2f}", fund_date))
        if ocf is not None:
            assessed.add("cash_flow")
            if ocf < 0:
                findings.append(_f("cash_flow", "HIGH", "Negative operating cash flow", f"OCF {ocf:,.0f}", fund_date))
        cc = m.get("cash_conversion")
        if cc is not None:
            assessed.add("profit_quality")
            if cc < 0.5:
                findings.append(_f("profit_quality", "MODERATE", "Weak cash conversion of profits", f"OCF/net profit {cc:.2f}", fund_date))
    if m:
        dil = m.get("shares_outstanding_growth")
        if dil is not None:
            assessed.add("dilution")
            if dil > 0.15:
                findings.append(_f("dilution", "HIGH", "Significant equity dilution", f"Share count up {dil:.1%} over available years", fund_date))
            elif dil > 0.05:
                findings.append(_f("dilution", "MODERATE", "Equity dilution", f"Share count up {dil:.1%} over available years", fund_date))
        sg = m.get("sales_growth_1y")
        if sg is not None and sg < 0:
            findings.append(_f("growth", "LOW", "Sales declined year over year", f"Sales growth {sg:.1%}", fund_date))
    if val:
        assessed.add("valuation")
        pe = val.get("ratios", {}).get("pe")
        if val.get("assessment") == "Expensive":
            mos = val.get("margin_of_safety")
            findings.append(_f("valuation", "MODERATE", "Valuation looks expensive vs modelled value", f"Margin of safety {mos:.1%}" if mos is not None else "PEG above 2", fund_date or mkt_date))
        elif pe is not None and pe > 60:
            findings.append(_f("valuation", "MODERATE", "Very high trailing P/E", f"P/E {pe:.1f}", mkt_date))
    tv = scout.get("avg_traded_value_20d_inr")
    if tv is not None:
        assessed.add("liquidity")
        if tv < 1e7:
            findings.append(_f("liquidity", "HIGH", "Thin trading liquidity", f"Avg daily traded value INR {tv/1e7:.2f} cr", mkt_date))
        elif tv < 5e7:
            findings.append(_f("liquidity", "MODERATE", "Limited trading liquidity", f"Avg daily traded value INR {tv/1e7:.2f} cr", mkt_date))
    vol = (tech.get("signals") or {}).get("volatility_ann")
    if vol is not None:
        assessed.add("volatility")
        if vol > 0.50:
            findings.append(_f("volatility", "HIGH", "Very high price volatility", f"Annualised volatility {vol:.0%}", mkt_date))
        elif vol > 0.35:
            findings.append(_f("volatility", "MODERATE", "High price volatility", f"Annualised volatility {vol:.0%}", mkt_date))
    if news is not None and news != {}:
        assessed.add("governance_news")
        hits = news.get("governance_hits", [])
        if hits:  # headlines alone can never produce CRITICAL: they are unverified
            sev = "HIGH" if len(hits) >= 2 else "MODERATE"
            findings.append(_f("governance_news", sev, "Governance/regulatory headlines need verification",
                               "; ".join(h["headline"] for h in hits[:3]), (hits[0].get("published_at") or "")[:10] or None, verified=False))

    score = min(100, sum(WEIGHT[f["severity"]] for f in findings))
    sev = {f["severity"] for f in findings}
    cls = ("UNASSESSED" if len(assessed) < 3 else "CRITICAL" if "CRITICAL" in sev else "HIGH" if "HIGH" in sev or score >= 40
           else "MODERATE" if score >= 10 else "LOW")
    return {"data": {"risk_score": score, "risk_class": cls, "findings": findings, "assessed_checks": sorted(assessed),
                     "unassessed_checks": UNASSESSED, "scale": "0-100, higher = more risk",
                     "critical_alert": cls == "CRITICAL"},
            "missing": [f"{k}: {v}" for k, v in UNASSESSED.items()], "warnings": []}
