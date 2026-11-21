"""Floor activity log. Every floor writes here; Floor 00 (Central Command) reads it. Logging never breaks real work."""
import logging
from datetime import timedelta

from database.connection import session_scope
from database.models import FloorActivity
from services.clock import utc_naive

log = logging.getLogger(__name__)
FLOORS = {0: "Central Command", 1: "Market Scanner", 2: "AI Analyst", 3: "Risk Manager", 4: "Paper Executor",
          5: "Monitor & Alerts", 6: "Portfolio Manager", 7: "Final Decision Engine"}


def log_activity(floor, event, message, status="ok", payload=None, run_id=None, to_floor=None, factory=None):
    try:
        with session_scope(factory) as s:
            s.add(FloorActivity(floor=floor, to_floor=to_floor, event=event, status=status, message=message, payload=payload, run_id=run_id))
    except Exception:
        log.exception("could not write floor activity")


def _row(a):
    return {"time": a.created_at, "floor": a.floor, "to_floor": a.to_floor, "event": a.event, "status": a.status, "message": a.message, "payload": a.payload}


def recent(floor=None, limit=60, errors_only=False, factory=None):
    with session_scope(factory) as s:
        q = s.query(FloorActivity)
        if floor is not None:
            q = q.filter((FloorActivity.floor == floor) | (FloorActivity.to_floor == floor))
        if errors_only:
            q = q.filter(FloorActivity.status == "error")
        return [_row(a) for a in q.order_by(FloorActivity.id.desc()).limit(limit)]


def floor_status(floor, active_window_s=90, factory=None):
    """ACTIVE = event in last 90s; ERROR = latest event is an error in last hour; IDLE = has history; else NO ACTIVITY YET."""
    with session_scope(factory) as s:
        last = s.query(FloorActivity).filter(FloorActivity.floor == floor).order_by(FloorActivity.id.desc()).first()
        errs = s.query(FloorActivity).filter(FloorActivity.floor == floor, FloorActivity.status == "error",
                                             FloorActivity.created_at >= utc_naive() - timedelta(hours=24)).count()
        if last is None:
            return {"state": "NO ACTIVITY YET", "last_event": None, "last_at": None, "errors_24h": errs}
        age = (utc_naive() - last.created_at).total_seconds()
        state = "ERROR" if last.status == "error" and age < 3600 else "ACTIVE" if age <= active_window_s else "IDLE"
        return {"state": state, "last_event": last.message, "last_at": last.created_at, "errors_24h": errs}


def active_links(window_s=60, factory=None):
    """(from_floor, to_floor) hand-offs seen recently; the building view animates only these."""
    with session_scope(factory) as s:
        cutoff = utc_naive() - timedelta(seconds=window_s)
        rows = s.query(FloorActivity.floor, FloorActivity.to_floor).filter(FloorActivity.to_floor.isnot(None), FloorActivity.created_at >= cutoff).distinct().all()
        return [(a, b) for a, b in rows]
