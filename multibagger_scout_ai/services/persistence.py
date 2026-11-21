"""Persist one analysis. Historical statements/prices are append-only; nothing is silently overwritten."""
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from database.models import (AgentOutput, AgentRun, Company, DataQualityLog, DataSource, ExchangeSymbol, FinancialStatement,
                             MarketPrice, NewsArticle, ResearchReport, ResearchScore, RiskFinding)
from services.serialization import to_jsonable

STMT_TYPES = {"annual_income": ("income", "annual"), "annual_balance": ("balance", "annual"),
              "annual_cashflow": ("cashflow", "annual"), "quarterly_income": ("income", "quarterly")}


def _symbol_row(s, result):
    scout = result["agents"]["stock_scout"]
    if scout["status"] not in ("ok", "partial"):
        return None
    d = scout["data"]
    es = s.query(ExchangeSymbol).filter_by(exchange=result["exchange"], symbol=result["symbol"]).one_or_none()
    if es is None:
        comp = Company(name=d.get("company_name") or result["symbol"], sector=d.get("sector"), industry=d.get("industry"))
        s.add(comp)
        s.flush()
        es = ExchangeSymbol(company_id=comp.id, exchange=result["exchange"], symbol=result["symbol"])
        s.add(es)
        s.flush()
    elif d.get("sector") or d.get("company_name"):
        es.company.sector = d.get("sector") or es.company.sector
        es.company.industry = d.get("industry") or es.company.industry
    return es


def save_analysis(s, result, history=None, statements=None):
    prov = result["provider"]
    es = _symbol_row(s, result)
    src = s.query(DataSource).filter_by(name=prov["name"]).one_or_none() or DataSource(name=prov["name"])
    s.add(src)
    now = datetime.now(timezone.utc)
    if prov.get("fetch_error"):
        src.last_error, src.last_error_at = prov["fetch_error"], now
    else:
        src.last_success_at = now
    if prov.get("is_synthetic"):
        src.description = "SYNTHETIC TEST DATA"

    if es is not None and history is not None:
        have = {r[0] for r in s.query(MarketPrice.trade_date).filter_by(symbol_id=es.id, interval="1d", source=prov["name"])}
        rows = [MarketPrice(symbol_id=es.id, trade_date=d.to_pydatetime(), interval="1d", open=float(r.Open), high=float(r.High),
                            low=float(r.Low), close=float(r.Close), volume=float(r.Volume), source=prov["name"])
                for d, r in history.iterrows() if d.to_pydatetime() not in have]
        s.bulk_save_objects(rows)
    if es is not None and statements:
        for key, df in statements.items():
            stype, ptype = STMT_TYPES.get(key, (key, "annual"))
            for col in df.columns:
                payload = {str(k): (None if pd.isna(v) else float(v)) for k, v in df[col].items()}
                h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                pe = pd.Timestamp(col).to_pydatetime()
                if not s.query(FinancialStatement.id).filter_by(company_id=es.company_id, statement_type=stype, period_type=ptype,
                                                                 period_end=pe, source=prov["name"], content_hash=h).first():
                    s.add(FinancialStatement(company_id=es.company_id, statement_type=stype, period_type=ptype, period_end=pe,
                                             source=prov["name"], content_hash=h, payload=payload))
    news = result["agents"]["news"]
    if es is not None and news["status"] in ("ok", "partial"):
        seen = {k[0] for k in s.query(NewsArticle.title_key).filter_by(symbol_id=es.id)}
        for it in news["data"].get("items", []):
            if it["title_key"] not in seen:
                seen.add(it["title_key"])
                s.add(NewsArticle(symbol_id=es.id, headline=it["headline"], source=it.get("source"), published_at=it.get("published_at"),
                                  url=it.get("url"), sentiment=it["sentiment"], relevance=it["relevance"], verification_status=it["verification_status"],
                                  title_key=it["title_key"]))
    for name, a in result["agents"].items():
        run = AgentRun(run_id=result["run_id"], symbol=result["symbol"], exchange=result["exchange"], agent=name, status=a["status"],
                       error=a.get("error"), started_at=a.get("started_at"), finished_at=a.get("finished_at"))
        s.add(run)
        s.flush()
        s.add(AgentOutput(agent_run_id=run.id, payload=to_jsonable({"data": a["data"], "missing": a["missing"], "warnings": a["warnings"]})))
    risk = result["agents"]["risk"]
    for f in (risk["data"].get("findings", []) if risk["status"] in ("ok", "partial") else []):
        s.add(RiskFinding(run_id=result["run_id"], symbol=result["symbol"], **{k: f[k] for k in ("category", "severity", "title", "evidence", "as_of", "verified")}))
    sc = result.get("scores") or {}
    hz = result.get("horizon_scores") or {}
    g = lambda k: (sc.get(k) or {}).get("score")
    s.add(ResearchScore(run_id=result["run_id"], symbol=result["symbol"], exchange=result["exchange"], fundamental=g("fundamental"),
                        technical=g("technical"), data_confidence=g("data_confidence"), risk=g("risk"), long_term=hz.get("long_term"),
                        short_term=hz.get("short_term"), balanced=hz.get("balanced"), risk_class=(sc.get("risk") or {}).get("class"),
                        tags=[t["tag"] for t in result.get("tags", [])], is_synthetic=bool(prov.get("is_synthetic"))))
    for msg in result.get("data_quality", []):
        s.add(DataQualityLog(run_id=result["run_id"], symbol=result["symbol"], provider=prov["name"], level=msg["level"], message=msg["message"]))
    for fmt, path in (result.get("report_paths") or {}).items():
        s.add(ResearchReport(run_id=result["run_id"], symbol=result["symbol"], exchange=result["exchange"], fmt=fmt, path=str(path)))
