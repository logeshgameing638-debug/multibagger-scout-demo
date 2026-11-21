"""AGENT 4 - Business quality. Evidence-based financial-quality PROXY only; no moat is claimed without evidence."""
CHECK_MISSING = "not evaluable"


def _checks(m, hist, fin):
    out = []
    thr, key = (0.12, "roe") if fin else (0.15, "roce")
    v = m.get(key)
    out.append(("Returns on capital", None if v is None else v >= thr, f"{key.upper()} {v:.1%} vs {thr:.0%} threshold" if v is not None else CHECK_MISSING))
    rev, ebit = list(hist.get("revenue", {}).values()), hist.get("operating_income", {})
    margins = [ebit[d] / hist["revenue"][d] for d in hist.get("revenue", {}) if d in ebit and ebit[d] is not None and hist["revenue"][d]]
    if len(margins) >= 3 and not fin:
        ok = min(margins) > 0 and (max(margins) - min(margins)) <= 0.08
        out.append(("Operating margin stability", ok, f"range {min(margins):.1%} to {max(margins):.1%} over {len(margins)} years"))
    else:
        out.append(("Operating margin stability", None, CHECK_MISSING))
    if len(rev) >= 3 and all(x is not None for x in rev):
        grew = all(rev[i] > rev[i + 1] for i in range(len(rev) - 1))  # latest first
        out.append(("Consistent sales growth", grew, f"sales rose in {sum(rev[i] > rev[i+1] for i in range(len(rev)-1))} of {len(rev)-1} transitions"))
    else:
        out.append(("Consistent sales growth", None, CHECK_MISSING))
    cc = m.get("cash_conversion")
    out.append(("Profits backed by cash", None if cc is None or fin else cc >= 0.7, f"OCF/net profit {cc:.2f}" if cc is not None and not fin else CHECK_MISSING))
    ni = [x for x in hist.get("net_income", {}).values() if x is not None]
    out.append(("Profitable every year on record", None if len(ni) < 3 else all(x > 0 for x in ni), f"{len(ni)} years checked" if len(ni) >= 3 else CHECK_MISSING))
    return out


def run(info, fund):
    m, hist, fin = fund.get("metrics", {}), fund.get("history", {}), fund.get("is_financial", False)
    checks = _checks(m, hist, fin) if m else []
    evaluable = [c for c in checks if c[1] is not None]
    passed, failed = sum(1 for c in evaluable if c[1]), sum(1 for c in evaluable if not c[1])
    if len(evaluable) < 3:
        cls = "Insufficient evidence"
    elif passed >= 4 or (passed >= 3 and failed == 0 and len(evaluable) == 3):
        cls = "Strong business"
    elif failed >= 3:
        cls = "Weak business"
    else:
        cls = "Average business"
    summary = (info or {}).get("longBusinessSummary")
    return {"data": {
        "classification": cls, "basis": "Financial-quality proxy from reported statements (not a qualitative moat assessment)",
        "checks": [{"check": n, "passed": ok, "evidence": ev} for n, ok, ev in checks],
        "evaluable_checks": len(evaluable), "passed_checks": passed,
        "moat": "Not assessed: no evidence on competitive advantage was collected", "business_summary_source": "Yahoo Finance (company-provided)" if summary else None,
        "business_summary": (summary[:600] + "...") if summary and len(summary) > 600 else summary,
        "sector": (info or {}).get("sector"), "industry": (info or {}).get("industry")},
        "missing": ["market share", "competitor comparison", "customer concentration", "supplier dependency", "expansion projects",
                    "order book", "management quality", "corporate governance (need filings/announcement connectors; not built)"],
        "warnings": []}
