"""Floor 00 task queue with retry. Failed work is retried up to max_attempts, then left visibly 'failed'."""
import logging

from database.connection import session_scope
from database.models import Task
from services.activity import log_activity
from services.clock import utc_naive

log = logging.getLogger(__name__)


def enqueue(kind, payload=None, max_attempts=3, factory=None):
    with session_scope(factory) as s:
        t = Task(kind=kind, payload=payload or {}, max_attempts=max_attempts)
        s.add(t)
        s.flush()
        return t.id


def run_queue(handlers, limit=100, factory=None):
    counts = {"done": 0, "retry": 0, "failed": 0}
    for _ in range(limit):
        with session_scope(factory) as s:
            t = s.query(Task).filter(Task.status == "queued").order_by(Task.id).first()
            if t is None:
                break
            t.status, t.attempts, t.started_at = "running", t.attempts + 1, utc_naive()
            tid, kind, payload, attempts, mx = t.id, t.kind, dict(t.payload or {}), t.attempts, t.max_attempts
        try:
            if kind not in handlers:
                raise KeyError(f"no handler for task kind '{kind}'")
            handlers[kind](payload)
            status, err = "done", None
        except Exception as exc:
            status, err = ("queued" if attempts < mx else "failed"), f"{type(exc).__name__}: {exc}"
            log.warning("task %s (%s) attempt %s failed: %s", tid, kind, attempts, err)
        with session_scope(factory) as s:
            t = s.get(Task, tid)
            t.status, t.last_error, t.finished_at = status, err, utc_naive()
        counts["done" if status == "done" else "retry" if status == "queued" else "failed"] += 1
        if status != "done":
            log_activity(0, "task_failed" if status == "failed" else "task_retry", f"{kind} attempt {attempts}/{mx}: {err}", "error", factory=factory)
    return counts


def queue_summary(factory=None):
    with session_scope(factory) as s:
        out = {k: s.query(Task).filter(Task.status == k).count() for k in ("queued", "running", "done", "failed")}
        recent = [{"id": t.id, "kind": t.kind, "status": t.status, "attempts": t.attempts, "error": t.last_error}
                  for t in s.query(Task).order_by(Task.id.desc()).limit(20)]
    return {"counts": out, "recent": recent}
