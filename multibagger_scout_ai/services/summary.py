from services.serialization import to_jsonable


def summarize(result):
    sc = result.get("scores") or {}
    g = lambda k: (sc.get(k) or {}).get("score")
    return to_jsonable({
        "run_id": result["run_id"], "symbol": result["symbol"], "exchange": result["exchange"], "generated_at": result["generated_at"],
        "provider": result["provider"], "agent_status": {n: a["status"] for n, a in result["agents"].items()},
        "scores": {"fundamental": g("fundamental"), "technical": g("technical"), "data_confidence": g("data_confidence"), "risk": g("risk"),
                   "risk_class": (sc.get("risk") or {}).get("class")},
        "horizon_scores": result.get("horizon_scores"), "tags": result.get("tags"), "warnings": result.get("warnings"),
        "report_paths": result.get("report_paths")})
