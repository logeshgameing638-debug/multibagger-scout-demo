"""Floor 03 Risk Manager: risk/reward, position sizing, exposure, approval. Research only; no order is ever sent anywhere."""
import math

LEVELS = {"reject": 2, "review": 1}


def _chk(name, ok, detail, level=None):
    return {"check": name, "ok": ok, "level": None if ok else level, "detail": detail}


def assess_trade(result, capital, risk_pct=1.0, max_position_pct=10.0, max_sector_pct=30.0, sector_value=0.0):
    ag = result["agents"]
    d = lambda n: ag[n]["data"] if ag[n]["status"] in ("ok", "partial") else {}
    scout, tech, risk = d("stock_scout"), d("technical"), d("risk")
    if not scout or not tech:
        return {"verdict": "REJECT", "reasons": ["No validated price/technical data; cannot size a trade."], "checks": [], "label": "RESEARCH ONLY"}
    entry = scout["last_price"]
    lv, sg, dm = tech.get("levels", {}), tech.get("signals", {}), tech.get("daily", {})
    stop, atr, res = lv.get("invalidation"), dm.get("atr14"), sg.get("resistance")
    checks = []
    rc = risk.get("risk_class", "UNASSESSED")
    checks.append(_chk("Critical risk", rc != "CRITICAL", f"risk class {rc}", "reject"))
    checks.append(_chk("Risk assessed", rc != "UNASSESSED", f"risk class {rc}", "review"))
    checks.append(_chk("High risk", rc != "HIGH", f"risk class {rc}", "review"))
    checks.append(_chk("Liquidity", scout.get("liquidity_class") != "LOW", f"avg traded value INR {scout.get('avg_traded_value_20d_inr', 0)/1e7:.2f} cr/day ({scout.get('liquidity_class')})", "reject"))
    out = {"label": "RESEARCH ONLY", "entry": entry, "stop": stop, "target": None, "target_basis": None, "risk_reward": None, "qty": 0,
           "position_value": 0.0, "risk_amount": 0.0, "risk_per_share": None, "checks": checks}
    valid_stop = stop is not None and 0 < stop < entry
    checks.append(_chk("Technical stop available", valid_stop, f"stop {stop}" if stop else "no ATR/support-based stop could be computed", "reject"))
    if valid_stop:
        rps = entry - stop
        if res is not None and res > entry:
            target, basis = res, "nearest swing resistance"
        elif atr:
            target, basis = entry + 3 * atr, "entry + 3 x ATR (no overhead resistance found)"
        else:
            target, basis = None, None
        out.update(risk_per_share=rps, target=target, target_basis=basis, extension_target_2r=entry + 2 * rps)
        if target:
            rr = (target - entry) / rps
            out["risk_reward"] = rr
            checks.append(_chk("Risk/reward >= 1", rr >= 1, f"R:R {rr:.2f} to {basis}", "reject"))
            checks.append(_chk("Risk/reward >= 2", rr >= 2, f"R:R {rr:.2f}", "review"))
        else:
            checks.append(_chk("Risk/reward computable", False, "no target basis", "review"))
        qty = math.floor(min(capital * risk_pct / 100 / rps, capital * max_position_pct / 100 / entry))
        out.update(qty=max(qty, 0), position_value=max(qty, 0) * entry, risk_amount=max(qty, 0) * rps)
        checks.append(_chk("Position size >= 1 share", qty >= 1, f"{qty} shares (risk {risk_pct}% of capital, cap {max_position_pct}% per position)", "reject"))
        sector_pct = (sector_value + out["position_value"]) / capital * 100 if capital else 0
        checks.append(_chk("Sector exposure", sector_pct <= max_sector_pct, f"sector would be {sector_pct:.1f}% of capital (limit {max_sector_pct}%)", "review"))
    worst = max((LEVELS[c["level"]] for c in checks if c["level"]), default=0)
    out["verdict"] = "REJECT" if worst == 2 else "REVIEW" if worst == 1 else "APPROVE"
    out["reasons"] = [f"{c['check']}: {c['detail']}" for c in checks if not c["ok"]] or ["All risk checks passed"]
    return out
