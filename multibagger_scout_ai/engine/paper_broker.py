"""Floor 04 Paper Executor. EVERYTHING HERE IS SIMULATED. No broker, no real orders, no live prices.
Fills happen at the last known delayed close +/- slippage."""
from database.models import PaperAccount, PaperOrder, PaperPosition
from services import settings_store
from services.clock import utc_naive

LABEL = "SIMULATED"


def get_account(s, factory=None):
    acc = s.query(PaperAccount).first()
    if acc is None:
        cap = settings_store.get_float("paper_capital", factory)
        acc = PaperAccount(starting_capital=cap, cash=cap)
        s.add(acc)
        s.flush()
    return acc


def place_order(s, symbol, exchange, side, qty, ref_price, ref_date=None, stop=None, target=None, sector=None, slippage_pct=0.1, factory=None):
    acc = get_account(s, factory)
    side = side.upper()
    reject = lambda why: _record(s, symbol, exchange, side, qty, ref_price, ref_date, None, "REJECTED", why)
    if side not in ("BUY", "SELL") or not isinstance(qty, int) or qty < 1 or ref_price is None or ref_price <= 0:
        return reject("invalid side, quantity or reference price")
    slip = slippage_pct / 100
    pos = s.query(PaperPosition).filter_by(symbol=symbol, exchange=exchange, status="OPEN").first()
    if side == "BUY":
        fill = ref_price * (1 + slip)
        cost = fill * qty
        if cost > acc.cash:
            return reject(f"insufficient simulated cash (need {cost:,.2f}, have {acc.cash:,.2f})")
        acc.cash -= cost
        if pos:
            pos.entry_price = (pos.entry_price * pos.qty + fill * qty) / (pos.qty + qty)
            pos.qty += qty
            pos.stop_loss, pos.target = stop or pos.stop_loss, target or pos.target
        else:
            s.add(PaperPosition(symbol=symbol, exchange=exchange, sector=sector, qty=qty, entry_price=fill, stop_loss=stop, target=target))
        return _record(s, symbol, exchange, side, qty, ref_price, ref_date, fill, "FILLED", "simulated fill at last known close + slippage")
    if pos is None or pos.qty < qty:
        return reject("no open simulated position large enough to sell")
    fill = ref_price * (1 - slip)
    _close(acc, pos, qty, fill, "MANUAL")
    return _record(s, symbol, exchange, side, qty, ref_price, ref_date, fill, "FILLED", "simulated fill at last known close - slippage")


def _record(s, symbol, exchange, side, qty, ref, ref_date, fill, status, reason):
    o = PaperOrder(symbol=symbol, exchange=exchange, side=side, qty=qty if isinstance(qty, int) else 0, ref_price=ref or 0.0, ref_price_date=ref_date, fill_price=fill, status=status, reason=reason)
    s.add(o)
    s.flush()
    return o


def _close(acc, pos, qty, price, reason):
    pnl = (price - pos.entry_price) * qty
    acc.cash += price * qty
    pos.realized_pnl = (pos.realized_pnl or 0.0) + pnl
    pos.qty -= qty
    if pos.qty == 0:
        pos.status, pos.closed_at, pos.exit_price, pos.exit_reason = "CLOSED", utc_naive(), price, reason


def check_exits(s, bars_fn, factory=None):
    """Close open simulated positions whose stop/target was touched by a completed daily bar after entry.
    If one bar touches both, the stop is assumed to hit first (conservative). Gap-through fills are NOT modelled."""
    acc, closed = get_account(s, factory), []
    for pos in s.query(PaperPosition).filter_by(status="OPEN"):
        if pos.stop_loss is None and pos.target is None:
            continue
        try:
            bars = bars_fn(pos.symbol, pos.exchange)
        except Exception:
            continue  # provider failure: leave position untouched and say nothing false
        for date, row in bars.iterrows():
            if date.to_pydatetime() <= pos.opened_at.replace(hour=0, minute=0, second=0, microsecond=0):
                continue
            if pos.stop_loss is not None and row["Low"] <= pos.stop_loss:
                qty = pos.qty
                _close(acc, pos, qty, pos.stop_loss, "STOP")
                _record(s, pos.symbol, pos.exchange, "SELL", qty, pos.stop_loss, date.date().isoformat(), pos.stop_loss, "FILLED", "simulated stop-loss touched")
                closed.append((pos.symbol, "STOP"))
                break
            if pos.target is not None and row["High"] >= pos.target:
                qty = pos.qty
                _close(acc, pos, qty, pos.target, "TARGET")
                _record(s, pos.symbol, pos.exchange, "SELL", qty, pos.target, date.date().isoformat(), pos.target, "FILLED", "simulated target touched")
                closed.append((pos.symbol, "TARGET"))
                break
    return closed
