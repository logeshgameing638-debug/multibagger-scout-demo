"""Floor 07 Final Decision Engine: consolidates scores, risk and trade assessment into APPROVE / REJECT / WATCHLIST with reasons.
APPROVE only means 'worth paper-trading / deeper study'. It is not a recommendation to buy."""

THRESH = {"approve_balanced": 55.0, "min_confidence_approve": 50.0, "reject_confidence": 35.0, "min_fundamental_approve": 35.0}


def decide(result, assessment):
    sc, hz = result.get("scores") or {}, result.get("horizon_scores") or {}
    f, t = (sc.get("fundamental") or {}).get("score"), (sc.get("technical") or {}).get("score")
    if f is None or t is None or hz.get("balanced") is None:
        return None  # nothing to decide: an agent failed, and we do not guess
    conf, rc, bal = (sc.get("data_confidence") or {}).get("score") or 0, (sc.get("risk") or {}).get("class"), hz["balanced"]
    why, rej, app = [], [], []
    if rc == "CRITICAL":
        rej.append("Critical risk present: " + "; ".join(x for x in sc["risk"]["drivers"] if x.startswith("CRITICAL")))
    if assessment and assessment["verdict"] == "REJECT":
        rej.append("Risk Manager rejected the trade setup: " + "; ".join(assessment["reasons"][:3]))
    if conf < THRESH["reject_confidence"]:
        rej.append(f"Data confidence {conf:.0f}/100 is below {THRESH['reject_confidence']:.0f}: evidence too thin to rely on")
    cond = [(bal >= THRESH["approve_balanced"], f"balanced score {bal:.1f} (needs >= {THRESH['approve_balanced']:.0f})"),
            (conf >= THRESH["min_confidence_approve"], f"data confidence {conf:.0f} (needs >= {THRESH['min_confidence_approve']:.0f})"),
            (f >= THRESH["min_fundamental_approve"], f"fundamental score {f:.0f} (needs >= {THRESH['min_fundamental_approve']:.0f})"),
            (rc in ("LOW", "MODERATE"), f"risk class {rc} (needs LOW or MODERATE)"),
            (bool(assessment) and assessment["verdict"] == "APPROVE", f"Risk Manager verdict {assessment['verdict'] if assessment else 'n/a'} (needs APPROVE)")]
    for ok, text in cond:
        (app if ok else why).append(text)
    if rej:
        verdict, reasons = "REJECT", rej
    elif not why:
        verdict, reasons = "APPROVE", ["All approval conditions met: " + "; ".join(app)]
    else:
        verdict, reasons = "WATCHLIST", ["Not approved because: " + "; ".join(why), "Passed: " + ("; ".join(app) or "none")]
    return {"verdict": verdict, "reasons": reasons, "thresholds": THRESH, "scores": {"fundamental": f, "technical": t, "confidence": conf, "risk_class": rc, "balanced": bal},
            "disclaimer": "Research verdict for paper trading and study only; not investment advice."}
