"""HTML / JSON / CSV research reports. PDF is not implemented in this slice."""
import csv
import html
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from services.serialization import to_jsonable

fp = lambda x, d=1: "n/a" if x is None else f"{x * 100:.{d}f}%"
fn = lambda x, d=2: "n/a" if x is None else f"{x:,.{d}f}"
e = html.escape


def narrative(result):
    ag = result["agents"]
    g = lambda n: ag[n]["data"] if ag[n]["status"] in ("ok", "partial") else {}
    fund, tech, risk, sc = g("fundamental"), g("technical"), g("risk"), result.get("scores") or {}
    hz = result.get("horizon_scores") or {}
    strong, weak = [], []
    for k in ("fundamental", "technical"):
        for c in (sc.get(k) or {}).get("components", []):
            for p in c["parts"]:
                if p["points"] is None:
                    continue
                (strong if p["points"] >= 0.75 * p["max"] else weak if p["points"] == 0 else []).append(f"{p['name']} ({p['note']})")
    thesis = []
    cands = [t for t in result.get("tags", []) if t["tag"].startswith("Potential multibagger")]
    thesis.append(cands[0]["reason"] if cands else "No multibagger hypothesis is supported by the evidence collected.")
    if strong:
        thesis.append("Supporting evidence: " + "; ".join(strong[:4]))
    if weak:
        thesis.append("Weak/absent evidence: " + "; ".join(weak[:4]))
    thesis.append("This is a research hypothesis from limited free data, not advice or a forecast.")
    inv = []
    lv = (tech.get("levels") or {}).get("invalidation")
    if lv:
        inv.append(f"Technical: a completed daily close below {lv:,.2f} invalidates the current chart setup.")
    if fund and not fund.get("is_financial"):
        inv += ["Fundamental: operating cash flow turns negative, or debt/equity rises above 1.0.", "Fundamental: sales decline in two consecutive fiscal years."]
    inv += ["Risk: risk class escalates to HIGH or CRITICAL.", "Governance: official filings confirm an auditor resignation, qualified opinion or promoter-pledge invocation."]
    missing = []
    for n, a in ag.items():
        missing += [f"[{n}] {m}" for m in a["missing"]]
    t = tech.get("short_term") or {}
    lt = tech.get("long_term") or {}
    return {"short_term": f"Daily trend {t.get('assessment', 'n/a')}; short-term research score {fn(hz.get('short_term'), 1)}. " + "; ".join(t.get("basis", [])),
            "long_term": f"Long-term trend {lt.get('assessment', 'n/a')}; long-term research score {fn(hz.get('long_term'), 1)}. " + "; ".join(lt.get("basis", [])),
            "thesis": thesis, "invalidation": inv, "missing_evidence": missing}


def _table(rows, head=None):
    h = "".join(f"<th>{e(str(x))}</th>" for x in head) if head else ""
    b = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{'<thead><tr>' + h + '</tr></thead>' if h else ''}<tbody>{b}</tbody></table>"


def _kv(d, pct=()):
    return _table([(k, fp(v) if k in pct else fn(v) if isinstance(v, float) else ("n/a" if v is None else v)) for k, v in d.items() if not isinstance(v, (dict, list))])


def _score_block(s):
    if not s:
        return "<p class='warn'>Not computed (agent failed or skipped).</p>"
    rows = [(c["name"], p["name"], "n/a (unassessed)" if p["points"] is None else f"{p['points']}/{p['max']}", p["note"]) for c in s["components"] for p in c["parts"]]
    return (f"<p class='big'>{s['score']}/100 <span class='dim'>assessable {s['assessable_points']}/100, "
            f"normalised on assessed {s['normalized_on_assessed']}</span></p>" + _table(rows, ["Component", "Item", "Points", "Evidence"]))


CSS = ("body{background:#0b1426;color:#dbe4f3;font:15px/1.55 'Segoe UI',system-ui,sans-serif;margin:0;padding:28px;max-width:1080px;margin:auto}"
       "h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:30px 0 8px;padding-top:14px;border-top:1px solid #22345a}"
       "table{border-collapse:collapse;width:100%;margin:6px 0;display:block;overflow-x:auto}td,th{border-bottom:1px solid #1d2d50;padding:5px 10px;text-align:left;vertical-align:top}"
       "th{color:#8fa3c7;font-weight:600}.big{font-size:22px;margin:4px 0}.dim{font-size:13px;color:#8fa3c7}.good{color:#35c27a}.bad{color:#ef5b5b}"
       ".warn{color:#f2c94c}.banner{padding:10px 14px;border-radius:6px;margin:10px 0}.b-warn{background:#3a3210;border:1px solid #f2c94c}"
       ".b-crit{background:#3b1414;border:1px solid #ef5b5b}.b-syn{background:#2d1b3d;border:1px solid #b07cf0}a{color:#7fb0ff}")


def to_html(result):
    ag, sc, hz = result["agents"], result.get("scores") or {}, result.get("horizon_scores") or {}
    g = lambda n: ag[n]["data"] if ag[n]["status"] in ("ok", "partial") else {}
    scout, fund, tech, biz, val, news, risk = (g(n) for n in ("stock_scout", "fundamental", "technical", "business", "valuation", "news", "risk"))
    nar, prov = result["narrative"], result["provider"]
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>{e(result['symbol'])} research report</title><style>{CSS}</style></head><body>"]
    out.append(f"<h1>{e(scout.get('company_name') or result['symbol'])} <span class='dim'>{e(result['exchange'])}:{e(result['symbol'])}</span></h1>")
    out.append(f"<div class='dim'>Generated {e(result['generated_at'])} | Multibagger Scout AI | research tool, not investment advice</div>")
    if prov.get("is_synthetic"):
        out.append("<div class='banner b-syn'><b>SYNTHETIC TEST DATA.</b> Nothing in this report is real market data.</div>")
    if (sc.get("risk") or {}).get("class") == "CRITICAL":
        out.append("<div class='banner b-crit'><b>CRITICAL RISK:</b> " + e("; ".join(d for d in sc["risk"]["drivers"] if d.startswith("CRITICAL"))) + "</div>")
    for w in result.get("warnings", []):
        out.append(f"<div class='banner b-warn'>{e(w)}</div>")
    out.append("<h2>Agent execution</h2>" + _table([(n, a["status"].upper(), a["error"] or "", len(a["missing"])) for n, a in ag.items()], ["Agent", "Status", "Error / reason", "Missing items"]))
    out.append("<h2>1. Company profile</h2>" + (_kv({k: scout.get(k) for k in ("symbol", "exchange", "company_name", "sector", "industry", "market_cap", "last_price", "last_price_date", "liquidity_class", "avg_traded_value_20d_inr")}) if scout else "<p class='warn'>Unavailable</p>"))
    out.append(f"<h2>2. Source and data timestamp</h2><p>Provider: {e(prov['name'])}. Fetched {e(str(prov.get('fetched_at')))}. Last price bar: {e(str(scout.get('last_price_date')))}. {e(prov.get('note') or '')}</p>")
    m = fund.get("metrics", {})
    pct_keys = {k for k in m if any(x in k for x in ("growth", "cagr", "roe", "roce", "margin", "holding", "conversion")) and "shares" not in k}
    out.append("<h2>3. Financial analysis</h2>" + (_kv(m, pct_keys) + ("<p class='warn'>Red flags: " + e("; ".join(fund.get("red_flags", [])) or "none detected") + "</p>") if fund else "<p class='warn'>Unavailable</p>"))
    d = tech.get("daily") or {}
    out.append("<h2>4. Technical analysis</h2>" + (f"<p>As of {e(tech['as_of'])} (completed candles). Trend: daily {e(tech['trend']['daily'])}, weekly {e(tech['trend']['weekly'])}, monthly {e(tech['trend']['monthly'])}.</p>" + _kv({k: v for k, v in d.items()}) +
               "<h3>Signals and levels</h3>" + _kv({**{k: v for k, v in tech["signals"].items() if not isinstance(v, dict)}, **{f"level_{k}": (", ".join(fn(x) for x in v) if isinstance(v, list) else v) for k, v in tech["levels"].items() if v is not None}}) if tech else "<p class='warn'>Unavailable</p>"))
    out.append("<h2>5. Business quality</h2>" + (f"<p><b>{e(biz['classification'])}</b>. {e(biz['basis'])}. {e(biz['moat'])}.</p>" + _table([(c["check"], {True: "pass", False: "fail", None: "not evaluable"}[c["passed"]], c["evidence"]) for c in biz["checks"]], ["Check", "Result", "Evidence"]) if biz else "<p class='warn'>Unavailable</p>"))
    out.append("<h2>6. Valuation</h2>" + (f"<p><b>{e(val['assessment'])}</b>. {e(val['method'] or '')}</p>" + _kv(val["ratios"], {"dividend_yield"}) + "<h3>Assumptions</h3>" + _table([(k, v) for k, v in val["assumptions"].items()]) +
               ("<h3>Scenarios (illustrative)</h3>" + _table([(k, *[fn(x) if isinstance(x, float) else x for x in v.values()]) for k, v in val["scenarios"].items()]) if val.get("scenarios") else f"<p class='warn'>No intrinsic value computed: {e(str(val.get('reason')))}</p>") if val else "<p class='warn'>Unavailable</p>"))
    out.append("<h2>7. News intelligence</h2>" + (_table([(i["headline"], i.get("source") or "", (i.get("published_at") or "")[:10], i["sentiment"], i["verification_status"], i.get("url") or "") for i in news.get("items", [])], ["Headline", "Source", "Date", "Sentiment", "Verification", "URL"]) if news.get("items") else "<p class='dim'>No items (agent status: " + e(ag["news"]["status"]) + ")</p>"))
    out.append("<h2>8. Risk analysis</h2>" + (f"<p class='big'>{e(risk['risk_class'])} <span class='dim'>score {risk['risk_score']}/100, higher = more risk</span></p>" + _table([(f["severity"], f["title"], f["evidence"], f["as_of"] or "", "verified" if f["verified"] else "UNVERIFIED") for f in risk["findings"]], ["Severity", "Finding", "Evidence", "As of", "Verification"]) + "<h3>Unassessed checks</h3>" + _table(list(risk["unassessed_checks"].items())) if risk else "<p class='warn'>Unavailable</p>"))
    out.append("<h2>9. Fundamental score</h2>" + _score_block(sc.get("fundamental")))
    out.append("<h2>10. Technical score</h2>" + _score_block(sc.get("technical")))
    out.append("<h2>11. Data confidence</h2>" + _score_block(sc.get("data_confidence")))
    out.append("<h2>Combined research scores</h2>" + _table([(k, fn(hz.get(k), 1)) for k in ("long_term", "short_term", "balanced")]) + f"<p class='dim'>{e(hz.get('formula', ''))}</p>")
    out.append("<h2>Classification tags</h2>" + (_table([(t["tag"], t["reason"]) for t in result.get("tags", [])]) or ""))
    out.append(f"<h2>12. Short-term assessment</h2><p>{e(nar['short_term'])}</p><h2>13. Long-term assessment</h2><p>{e(nar['long_term'])}</p>")
    out.append("<h2>14. Investment thesis (research hypothesis)</h2>" + "".join(f"<p>{e(t)}</p>" for t in nar["thesis"]))
    out.append("<h2>15. Thesis invalidation conditions</h2><ul>" + "".join(f"<li>{e(t)}</li>" for t in nar["invalidation"]) + "</ul>")
    out.append("<h2>16. Missing evidence</h2><ul>" + "".join(f"<li>{e(t)}</li>" for t in nar["missing_evidence"]) + "</ul>")
    out.append("<h2>17. Sources</h2><ul>" + f"<li>{e(prov['name'])}: {e(prov.get('note') or '')}</li><li>rss_news: aggregator headlines (unverified)</li></ul></body></html>")
    return "".join(out)


def to_json(result):
    return json.dumps(to_jsonable(result), indent=2, ensure_ascii=False)


def to_csv(result):
    rows = []

    def walk(prefix, o):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(o, list):
            rows.append((prefix, json.dumps(o, ensure_ascii=False)))
        else:
            rows.append((prefix, o))

    walk("", to_jsonable({k: v for k, v in result.items() if k not in ("narrative",)}))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["path", "value"])
    w.writerows(rows)
    return buf.getvalue()


def export_all(result, out_dir=None):
    out = Path(out_dir or settings.EXPORT_DIR).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = "SYNTHETIC_" if result["provider"].get("is_synthetic") else ""
    base = f"{prefix}{result['symbol']}_{result['exchange']}_{ts}"
    paths = {}
    for fmt, fnc in (("html", to_html), ("json", to_json), ("csv", to_csv)):
        p = out / f"{base}.{fmt}"
        p.write_text(fnc(result), encoding="utf-8")
        paths[fmt] = str(p)
    return paths
