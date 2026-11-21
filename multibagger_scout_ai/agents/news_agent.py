"""AGENT 7 - News intelligence. Headlines are unverified signals, never confirmed evidence."""
import re

POS = ["order win", "wins order", "bags order", "secures", "record profit", "profit rises", "profit jumps", "net profit up",
       "upgrade", "beats estimates", "expansion", "new contract", "dividend", "approval", "acquires", "acquisition", "capacity addition"]
NEG = ["loss widens", "net loss", "profit falls", "profit drops", "downgrade", "misses estimates", "penalty", "fine", "probe", "raid",
       "fraud", "default", "insolvency", "nclt", "resigns", "resignation", "auditor", "sebi order", "sebi notice", "show cause",
       "pledge", "stake sale", "plunges", "slumps", "forensic audit", "qualified opinion", "downgraded"]
GOVERNANCE = ["auditor resign", "resigns as auditor", "auditor quits", "qualified opinion", "forensic audit", "fraud", "sebi order",
              "sebi notice", "show cause", "default", "insolvency", "nclt", "raid", "pledge invoked", "related party"]


def core_name(name, symbol):
    if not name:
        return symbol.lower()
    n = re.sub(r"\b(limited|ltd|incorporated|inc|corporation|corp)\b\.?", "", name.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]", " ", n)).strip() or symbol.lower()


def title_key(title):
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", title.lower())  # strip trailing " - Publisher"
    return re.sub(r"[^a-z0-9]", "", t)[:120]


def classify(title):
    t = title.lower()
    pos, neg = sum(k in t for k in POS), sum(k in t for k in NEG)
    return "Positive" if pos > neg else "Negative" if neg > pos else "Neutral"


def run(company_name, symbol, connector):
    core = core_name(company_name, symbol)
    raw = connector.fetch(f'"{core}" when:30d')  # connector errors propagate: agent is recorded as failed
    seen, items, dropped = set(), [], 0
    for it in raw:
        key = title_key(it["headline"])
        if key in seen:
            continue
        seen.add(key)
        if core not in it["headline"].lower():
            dropped += 1
            continue
        items.append({**it, "company": company_name or symbol, "title_key": key, "sentiment": classify(it["headline"]),
                      "relevance": "high", "verification_status": "unverified_headline"})
    gov = [i for i in items if any(k in i["headline"].lower() for k in GOVERNANCE)]
    counts = {s: sum(i["sentiment"] == s for i in items) for s in ("Positive", "Negative", "Neutral")}
    warnings = ["Headlines come from an aggregator feed and are unverified; official NSE/BSE announcements are not yet connected."]
    if dropped:
        warnings.append(f"{dropped} low-relevance headlines dropped (company name not in headline)")
    if not items:
        warnings.append("No recent relevant headlines found. Absence of news is not evidence of absence of problems.")
    return {"data": {"items": items, "counts": counts, "governance_hits": gov, "query_core_name": core, "source": "rss_news"},
            "missing": ["official corporate announcements (NSE/BSE connector not built)", "quarterly results/annual report detection"],
            "warnings": warnings}
