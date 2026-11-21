"""Floor 06 Portfolio Manager: SIMULATED portfolio. Prices are the last known delayed close with their date."""
from database.models import MarketPrice, ExchangeSymbol, PaperPosition, PortfolioSnapshot
from engine import paper_broker


def latest_price(s, symbol, exchange, provider=None):
    """Prefer a fresh provider quote (delayed daily close); fall back to the last stored close. Always returns its date and source."""
    if provider is not None:
        try:
            h = provider.fetch_history(symbol, exchange, period="1mo")
            return {"price": float(h["Close"].iloc[-1]), "date": h.index[-1].date().isoformat(), "source": getattr(provider, "name", "provider") + " (delayed)"}
        except Exception:
            pass
    row = (s.query(MarketPrice).join(ExchangeSymbol, MarketPrice.symbol_id == ExchangeSymbol.id)
           .filter(ExchangeSymbol.symbol == symbol, ExchangeSymbol.exchange == exchange).order_by(MarketPrice.trade_date.desc()).first())
    return {"price": row.close, "date": row.trade_date.date().isoformat(), "source": f"{row.source} (stored, delayed)"} if row else None


def summary(s, provider=None, factory=None):
    acc = paper_broker.get_account(s, factory)
    rows, value = [], 0.0
    for p in s.query(PaperPosition).filter_by(status="OPEN").order_by(PaperPosition.id):
        lp = latest_price(s, p.symbol, p.exchange, provider)
        price = lp["price"] if lp else None
        mv = price * p.qty if price else None
        value += mv if mv is not None else p.entry_price * p.qty  # unpriced holdings valued at cost and flagged
        rows.append({"symbol": p.symbol, "exchange": p.exchange, "sector": p.sector or "Unknown", "qty": p.qty, "entry": p.entry_price,
                     "stop": p.stop_loss, "target": p.target, "last": price, "price_date": lp["date"] if lp else None,
                     "price_source": lp["source"] if lp else "NO PRICE AVAILABLE (valued at cost)",
                     "unrealized_pnl": (price - p.entry_price) * p.qty if price else None,
                     "unrealized_pct": (price / p.entry_price - 1) if price else None, "market_value": mv})
    realized = sum(p.realized_pnl or 0.0 for p in s.query(PaperPosition))
    equity = acc.cash + value
    sectors = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0.0) + (r["market_value"] or r["entry"] * r["qty"])
    return {"label": paper_broker.LABEL, "starting_capital": acc.starting_capital, "cash": acc.cash, "positions_value": value, "equity": equity,
            "total_return": equity / acc.starting_capital - 1, "realized_pnl": realized,
            "unrealized_pnl": sum(r["unrealized_pnl"] or 0.0 for r in rows), "holdings": rows,
            "sector_exposure_pct": {k: v / equity * 100 for k, v in sectors.items()} if equity else {},
            "largest_position_pct": max(((r["market_value"] or r["entry"] * r["qty"]) / equity * 100 for r in rows), default=0.0) if equity else 0.0}


def snapshot(s, provider=None, factory=None):
    sm = summary(s, provider, factory)
    s.add(PortfolioSnapshot(equity=sm["equity"], cash=sm["cash"], positions_value=sm["positions_value"]))
    return sm


def performance(s):
    snaps = s.query(PortfolioSnapshot).order_by(PortfolioSnapshot.taken_at).all()
    eq = [x.equity for x in snaps]
    peak, mdd = (eq[0] if eq else 0), 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1 if peak else 0)
    return {"points": [(x.taken_at, x.equity) for x in snaps], "max_drawdown": mdd if eq else None,
            "note": "Needs at least 2 daily snapshots to show a curve." if len(eq) < 2 else ""}
