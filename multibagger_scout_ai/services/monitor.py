"""Floor 05 Monitor & Alerts. Rules compare the newest research run with the previous one. Alerts are de-duplicated for 24h."""
from datetime import timedelta

from config import settings
from database.models import Alert, Decision, PriceAlertRule, ResearchScore
from services.clock import utc_naive

RANK = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


def _add(s, symbol, exchange, kind, severity, message, run_id):
    since = utc_naive() - timedelta(hours=24)
    if s.query(Alert.id).filter(Alert.symbol == symbol, Alert.exchange == exchange, Alert.kind == kind, Alert.message == message, Alert.created_at >= since).first():
        return None
    a = Alert(symbol=symbol, exchange=exchange, kind=kind, severity=severity, message=message, run_id=run_id)
    s.add(a)
    return a


def evaluate(s, result, decision):
    """Create alerts for one fresh analysis result. Call BEFORE the new score row is saved, or pass exclude via run_id."""
    sym, ex, rid = result["symbol"], result["exchange"], result["run_id"]
    sc, made = result.get("scores") or {}, []
    prev = s.query(ResearchScore).filter(ResearchScore.symbol == sym, ResearchScore.exchange == ex, ResearchScore.run_id != rid).order_by(ResearchScore.created_at.desc()).first()
    add = lambda *a: made.append(_add(s, sym, ex, *a, rid))
    rc = (sc.get("risk") or {}).get("class")
    if rc == "CRITICAL":
        add("critical_risk", "CRITICAL", "Critical risk: " + "; ".join(x for x in sc["risk"]["drivers"] if x.startswith("CRITICAL")))
    if prev and prev.risk_class in RANK and rc in RANK and RANK[rc] > RANK[prev.risk_class]:
        add("risk_escalation", "HIGH", f"Risk class rose from {prev.risk_class} to {rc}")
    bal = (result.get("horizon_scores") or {}).get("balanced")
    if prev and prev.balanced is not None and bal is not None and abs(bal - prev.balanced) >= settings.SCORE_CHANGE_ALERT_POINTS:
        add("score_change", "INFO", f"Balanced score moved {prev.balanced:.1f} -> {bal:.1f}")
    tech = result["agents"]["technical"]["data"] if result["agents"]["technical"]["status"] in ("ok", "partial") else {}
    if (tech.get("signals") or {}).get("breakout_confirmed"):
        add("breakout", "INFO", f"Confirmed breakout on completed daily candle (as of {tech.get('as_of')})")
    for n, a in result["agents"].items():
        if a["status"] == "failed":
            add("agent_failure", "WARN", f"Agent {n} failed: {a['error']}")
    news = result["agents"]["news"]["data"] if result["agents"]["news"]["status"] in ("ok", "partial") else {}
    for h in news.get("governance_hits", [])[:2]:
        add("news", "WARN", f"Unverified governance/regulatory headline: {h['headline'][:140]}")
    if decision:
        pd_ = s.query(Decision).filter(Decision.symbol == sym, Decision.exchange == ex, Decision.run_id != rid).order_by(Decision.created_at.desc()).first()
        if pd_ and pd_.verdict != decision["verdict"]:
            add("decision_change", "INFO", f"Verdict changed {pd_.verdict} -> {decision['verdict']}")
    return [a for a in made if a is not None]


def check_price_rules(s, provider):
    """User price rules checked against the last delayed daily close (not live)."""
    fired = []
    for r in s.query(PriceAlertRule).filter_by(active=True):
        try:
            h = provider.fetch_history(r.symbol, r.exchange, period="1mo")
        except Exception:
            continue
        px, d = float(h["Close"].iloc[-1]), h.index[-1].date().isoformat()
        if (r.direction == "above" and px >= r.price) or (r.direction == "below" and px <= r.price):
            r.active, r.triggered_at = False, utc_naive()
            a = _add(s, r.symbol, r.exchange, "price", "INFO", f"Price rule hit: close {px:.2f} ({d}, delayed) is {r.direction} {r.price:.2f}", None)
            if a:
                fired.append(a)
    return fired


def open_alerts(s, limit=100):
    return [{"time": a.created_at, "symbol": a.symbol, "exchange": a.exchange, "kind": a.kind, "severity": a.severity, "message": a.message, "id": a.id}
            for a in s.query(Alert).filter_by(acknowledged=False).order_by(Alert.id.desc()).limit(limit)]
