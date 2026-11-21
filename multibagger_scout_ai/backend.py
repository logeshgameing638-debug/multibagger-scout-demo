"""FastAPI backend. Local use: 127.0.0.1 only. If you ever expose it, set API_KEY and keep the rate limit."""
import collections
import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import settings
from data.validation import validate_symbol
from database.connection import get_factory, session_scope
from database.models import ResearchReport
from engine.orchestrator import analyze
from services import queries, watchlist
from services.serialization import to_jsonable
from services.summary import summarize

app = FastAPI(title="Multibagger Scout AI", version="0.1.0")
_hits = collections.defaultdict(collections.deque)


def guard(request: Request, x_api_key: str = Header(default=None)):
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(401, "invalid API key")
    q, now = _hits[request.client.host if request.client else "unknown"], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "rate limit exceeded")
    q.append(now)


def get_provider():
    return None  # None -> default YahooConnector; tests override this dependency


def get_news():
    return None


def get_session_factory():
    return get_factory()


class AnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    exchange: Literal["NSE", "BSE"] = "NSE"


@app.get("/health")
def health(factory=Depends(get_session_factory)):
    with session_scope(factory) as s:
        counts = queries.table_counts(s)
    return {"status": "ok", "database": "ok", "rows": counts}


@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest, provider=Depends(get_provider), news=Depends(get_news), factory=Depends(get_session_factory), _=Depends(guard)):
    try:
        symbol = validate_symbol(req.symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return summarize(analyze(symbol, req.exchange, provider=provider, news=news, session_factory=factory))


@app.get("/scores")
def scores(factory=Depends(get_session_factory), _=Depends(guard)):
    with session_scope(factory) as s:
        return to_jsonable(queries.latest_scores(s))


@app.get("/alerts")
def alerts(factory=Depends(get_session_factory), _=Depends(guard)):
    with session_scope(factory) as s:
        return to_jsonable(queries.recent_alerts(s))


@app.get("/watchlist")
def get_watchlist(factory=Depends(get_session_factory), _=Depends(guard)):
    with session_scope(factory) as s:
        return to_jsonable(watchlist.entries(s))


@app.post("/watchlist")
def add_watchlist(req: AnalyzeRequest, factory=Depends(get_session_factory), _=Depends(guard)):
    try:
        with session_scope(factory) as s:
            row = watchlist.add(s, req.symbol, req.exchange)
            return {"symbol": row.symbol, "exchange": row.exchange, "enabled": row.enabled}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/reports/{symbol}/{fmt}")
def report(symbol: str, fmt: Literal["html", "json", "csv"], factory=Depends(get_session_factory), _=Depends(guard)):
    try:
        symbol = validate_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with session_scope(factory) as s:
        row = s.query(ResearchReport).filter_by(symbol=symbol, fmt=fmt).order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc()).first()
        path = row.path if row else None
    if not path:
        raise HTTPException(404, "no report stored for that symbol")
    p = __import__("pathlib").Path(path).resolve()
    if not p.is_relative_to(settings.EXPORT_DIR) or not p.is_file():  # never serve files outside the export folder
        raise HTTPException(404, "report file unavailable")
    return FileResponse(p)
