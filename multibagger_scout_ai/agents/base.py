"""Common agent contract. Status is never faked: failures and skips are recorded as such."""
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


@dataclass
class AgentResult:
    agent: str
    status: str = "skipped"  # ok | partial | failed | skipped
    data: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    error: str = None
    started_at: str = None
    finished_at: str = None
    duration_s: float = None

    def to_dict(self):
        return asdict(self)


def run_agent(name, fn, *args, required=(), **kwargs) -> AgentResult:
    """Run an agent. Agents return {"data":..., "missing":[...], "warnings":[...]}; output is validated."""
    res = AgentResult(agent=name, started_at=utcnow().isoformat())
    t0 = time.perf_counter()
    try:
        out = fn(*args, **kwargs)
        if not isinstance(out, dict) or not isinstance(out.get("data"), dict):
            raise ValueError("agent returned an invalid output structure")
        absent = [k for k in required if k not in out["data"]]
        if absent:
            raise ValueError(f"agent output missing required keys: {absent}")
        res.data, res.missing, res.warnings = out["data"], list(out.get("missing", [])), list(out.get("warnings", []))
        res.status = "partial" if res.missing else "ok"
    except Exception as exc:
        log.exception("agent %s failed", name)
        res.status, res.error = "failed", f"{type(exc).__name__}: {exc}"
    res.finished_at = utcnow().isoformat()
    res.duration_s = round(time.perf_counter() - t0, 3)
    return res


def skipped(name, reason) -> AgentResult:
    return AgentResult(agent=name, status="skipped", error=reason)


def usable(res: AgentResult) -> dict:
    """Data of an agent that actually produced output, else {}."""
    return res.data if res is not None and res.status in ("ok", "partial") else {}
