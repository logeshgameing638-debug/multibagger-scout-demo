"""Horizon scores, classification tags and ranking. Tags are research hypotheses, never guarantees."""


def horizon_scores(f, t):
    if f is None or t is None:
        return {"long_term": None, "short_term": None, "balanced": None, "formula": "needs both fundamental and technical scores"}
    lt, st = 0.7 * f + 0.3 * t, 0.7 * t + 0.3 * f
    return {"long_term": round(lt, 2), "short_term": round(st, 2), "balanced": round(0.5 * lt + 0.5 * st, 2),
            "formula": "long=0.7F+0.3T; short=0.7T+0.3F; balanced=0.5*long+0.5*short"}


def classify_tags(agents, scores):
    g = lambda n: agents[n]["data"] if agents[n]["status"] in ("ok", "partial") else {}
    fund, tech, biz, val, risk = g("fundamental"), g("technical"), g("business"), g("valuation"), g("risk")
    m = fund.get("metrics", {})
    tags = []
    rc = (scores.get("risk") or {}).get("class")
    conf = (scores.get("data_confidence") or {}).get("score") or 0
    cov = (scores.get("fundamental") or {}).get("coverage") or 0
    ts = (scores.get("technical") or {}).get("score")
    if biz.get("classification") == "Strong business":
        tags.append({"tag": "High-quality business", "reason": f"{biz['passed_checks']} of {biz['evaluable_checks']} financial-quality checks passed (proxy)"})
    if val.get("assessment") == "Attractive":
        tags.append({"tag": "Attractive valuation", "reason": f"margin of safety {val['margin_of_safety']:.0%} on stated assumptions" if val.get("margin_of_safety") is not None else "PEG below 1"})
    if ts is not None and ts >= 65 and tech.get("trend", {}).get("daily") == "Bullish":
        tags.append({"tag": "Strong technical trend", "reason": f"technical score {ts:.0f}/100, daily trend Bullish"})
    if rc in ("HIGH", "CRITICAL"):
        tags.append({"tag": "High-risk stock", "reason": f"risk class {rc}"})
    insufficient = conf < 50 or cov < 0.4 or rc == "UNASSESSED"
    if insufficient:
        tags.append({"tag": "Insufficient evidence", "reason": f"data confidence {conf:.0f}, fundamental coverage {cov:.0%}, risk class {rc}"})
    fin = fund.get("is_financial", False)
    c3s, c3p = m.get("sales_cagr_3y"), m.get("profit_cagr_3y")
    ret = m.get("roe") if fin else m.get("roce")
    lev_ok = fin or (m.get("debt_to_equity") is not None and m["debt_to_equity"] <= 1)
    if (not insufficient and rc in ("LOW", "MODERATE") and biz.get("classification") != "Weak business" and c3s is not None and c3p is not None
            and c3s >= 0.15 and c3p >= 0.15 and ret is not None and ret >= 0.15 and lev_ok):
        tags.append({"tag": "Potential multibagger candidate (research hypothesis)",
                     "reason": f"3y sales CAGR {c3s:.0%}, profit CAGR {c3p:.0%}, {'ROE' if fin else 'ROCE'} {ret:.0%}, acceptable leverage, risk {rc}; NOT a prediction"})
    return tags


def rank(results):
    """Rank analyses by balanced score; critical-risk names stay visible with a flag, never hidden by their score."""
    rows = []
    for r in results:
        hz, sc = r.get("horizon_scores") or {}, r.get("scores") or {}
        rows.append({"symbol": r["symbol"], "exchange": r["exchange"], "balanced": hz.get("balanced"), "long_term": hz.get("long_term"),
                     "short_term": hz.get("short_term"), "fundamental": (sc.get("fundamental") or {}).get("score"),
                     "technical": (sc.get("technical") or {}).get("score"), "data_confidence": (sc.get("data_confidence") or {}).get("score"),
                     "risk": (sc.get("risk") or {}).get("score"), "risk_class": (sc.get("risk") or {}).get("class"),
                     "flag": "CRITICAL RISK" if (sc.get("risk") or {}).get("class") == "CRITICAL" else "", "tags": [t["tag"] for t in r.get("tags", [])]})
    rows.sort(key=lambda x: (x["balanced"] is None, -(x["balanced"] or 0)))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows
