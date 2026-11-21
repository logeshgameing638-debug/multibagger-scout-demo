from sqlalchemy import func, text

from database.models import Alert, Base, ResearchScore


def latest_scores(s, include_synthetic=False):
    rows = (s.query(ResearchScore).filter(ResearchScore.balanced.isnot(None))
            .order_by(ResearchScore.created_at.desc(), ResearchScore.id.desc()).all())
    seen, out = set(), []
    for r in rows:
        key = (r.symbol, r.exchange)
        if key in seen:
            continue
        seen.add(key)
        if r.is_synthetic and not include_synthetic:
            continue
        out.append({"symbol": r.symbol, "exchange": r.exchange, "balanced": r.balanced, "long_term": r.long_term, "short_term": r.short_term,
                    "fundamental": r.fundamental, "technical": r.technical, "data_confidence": r.data_confidence, "risk": r.risk,
                    "risk_class": r.risk_class, "tags": r.tags or [], "run_id": r.run_id, "scored_at": r.created_at})
    return out


def recent_alerts(s, limit=100, unacknowledged_only=False):
    q = s.query(Alert).order_by(Alert.created_at.desc(), Alert.id.desc())
    if unacknowledged_only:
        q = q.filter_by(acknowledged=False)
    return [{"id": a.id, "when": a.created_at, "symbol": a.symbol, "exchange": a.exchange, "kind": a.kind, "severity": a.severity,
             "message": a.message, "acknowledged": a.acknowledged} for a in q.limit(limit)]


def table_counts(s):
    return {t.name: s.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar() for t in Base.metadata.sorted_tables}
