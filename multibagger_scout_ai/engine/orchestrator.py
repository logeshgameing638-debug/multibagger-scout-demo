"""Master orchestrator: collect -> run 8 agents -> validate -> score -> rank tags -> report -> persist."""
import logging
import uuid
from datetime import datetime, timezone

from agents import (business_agent, fundamental_agent, news_agent, risk_agent, scoring_agent, stock_scout, technical_agent,
                    valuation_agent)
from agents.base import AgentResult, run_agent, skipped, usable
from data.connectors.rss_news import RssNewsConnector
from data.connectors.yahoo import YahooConnector
from data.validation import clean_ohlcv, validate_exchange, validate_symbol
from engine import ranking, report_generator
from services.serialization import to_jsonable

log = logging.getLogger(__name__)
AGENT_ORDER = ["stock_scout", "fundamental", "technical", "valuation", "business", "news", "risk", "scoring"]


def analyze(symbol, exchange="NSE", provider=None, news=None, persist=True, session_factory=None, export=True, export_dir=None, now=None):
    symbol, exchange = validate_symbol(symbol), validate_exchange(exchange)
    provider, news = provider or YahooConnector(), news or RssNewsConnector()
    run_id = uuid.uuid4().hex
    agents, dq, warnings = {}, [], []
    result = {"run_id": run_id, "symbol": symbol, "exchange": exchange, "generated_at": datetime.now(timezone.utc).isoformat(),
              "provider": {"name": getattr(provider, "name", "unknown"), "fetched_at": None, "errors": {}, "is_synthetic": False, "fetch_error": None, "note": ""},
              "agents": {}, "scores": None, "horizon_scores": None, "tags": [], "warnings": warnings, "data_quality": dq}
    history = statements = pr = None
    try:
        pr = provider.fetch(symbol, exchange)
    except Exception as exc:
        result["provider"]["fetch_error"] = str(exc)
        dq.append({"level": "ERROR", "message": f"provider {result['provider']['name']} failed: {exc}"})
        warnings.append(f"Data provider failed: {exc}. No analysis was produced; nothing was estimated.")

    if pr is not None:
        result["provider"].update(fetched_at=pr.fetched_at.isoformat(), errors=pr.errors, is_synthetic=pr.is_synthetic, note=pr.note)
        dq += [{"level": "WARN", "message": f"{k}: {v}"} for k, v in pr.errors.items()]
        try:
            history, issues = clean_ohlcv(pr.history)
            agents["stock_scout"] = run_agent("stock_scout", stock_scout.run, pr, history, issues, required=("symbol", "last_price"))
        except Exception as exc:
            agents["stock_scout"] = AgentResult(agent="stock_scout", status="failed", error=f"{type(exc).__name__}: {exc}")
    else:
        agents["stock_scout"] = AgentResult(agent="stock_scout", status="failed", error=result["provider"]["fetch_error"])

    if agents["stock_scout"].status in ("ok", "partial"):
        statements = pr.statements
        info = pr.info or {}
        scout = agents["stock_scout"].data
        agents["fundamental"] = run_agent("fundamental", fundamental_agent.run, pr, required=("metrics",))
        agents["technical"] = run_agent("technical", technical_agent.run, history, now, required=("daily", "signals", "trend"))
        fund, tech = usable(agents["fundamental"]), usable(agents["technical"])
        agents["valuation"] = run_agent("valuation", valuation_agent.run, info, scout["last_price"], fund, required=("ratios", "assessment"))
        agents["business"] = run_agent("business", business_agent.run, info, fund, required=("classification",))
        agents["news"] = run_agent("news", news_agent.run, scout.get("company_name"), symbol, news, required=("items",))
        val, nws = usable(agents["valuation"]), usable(agents["news"])
        agents["risk"] = run_agent("risk", risk_agent.run, info, scout, fund, val, nws, tech, required=("risk_class", "findings"))
        today = (now or datetime.now()).date()
        agents["scoring"] = run_agent("scoring", scoring_agent.run, result["provider"], scout, fund, tech, val, usable(agents["risk"]), info, today,
                                      required=("data_confidence",))
    else:
        for n in AGENT_ORDER[1:]:
            agents[n] = skipped(n, "no validated market data (stock_scout failed)")

    result["agents"] = {n: agents[n].to_dict() for n in AGENT_ORDER}
    sc = usable(agents["scoring"])
    if sc:
        result["scores"] = sc
        f, t = (sc["fundamental"] or {}).get("score"), (sc["technical"] or {}).get("score")
        result["horizon_scores"] = ranking.horizon_scores(f, t)
        result["tags"] = ranking.classify_tags(result["agents"], sc)
    for n, a in result["agents"].items():
        if a["status"] == "failed":
            warnings.append(f"Agent '{n}' FAILED: {a['error']}")
    if (sc.get("risk") or {}).get("class") == "CRITICAL":
        warnings.append("CRITICAL RISK flagged. Review risk findings before reading any score.")
    tech_d = usable(agents["technical"])
    if tech_d.get("provisional_bar"):
        warnings.append("Today's session is still open; the in-progress bar is provisional and excluded from signals.")
    if result["provider"]["is_synthetic"]:
        warnings.append("SYNTHETIC TEST DATA: not real market data.")
    result["narrative"] = report_generator.narrative(result)
    if export:
        try:
            result["report_paths"] = report_generator.export_all(result, export_dir)
        except Exception as exc:
            log.exception("report export failed")
            warnings.append(f"Report export failed: {exc}")
    if persist:
        try:
            from database.connection import session_scope
            from services.persistence import save_analysis
            with session_scope(session_factory) as s:
                save_analysis(s, to_jsonable_safe(result), history, statements)
        except Exception as exc:
            log.exception("persistence failed")
            warnings.append(f"Database save failed: {exc}")
    result["_history"], result["_statements"] = history, statements
    return result


def to_jsonable_safe(result):
    return result  # persistence uses plain dicts already; helper kept for a single seam
