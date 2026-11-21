from data.validation import validate_exchange, validate_symbol
from database.models import Watchlist


def add(s, symbol, exchange="NSE", note=None):
    symbol, exchange = validate_symbol(symbol), validate_exchange(exchange)
    row = s.query(Watchlist).filter_by(symbol=symbol, exchange=exchange).one_or_none()
    if row is None:
        row = Watchlist(symbol=symbol, exchange=exchange, note=note)
        s.add(row)
    else:
        row.enabled = True
    s.flush()
    return row


def remove(s, symbol, exchange="NSE"):
    return s.query(Watchlist).filter_by(symbol=validate_symbol(symbol), exchange=validate_exchange(exchange)).delete()


def set_enabled(s, symbol, exchange, enabled):
    row = s.query(Watchlist).filter_by(symbol=validate_symbol(symbol), exchange=validate_exchange(exchange)).one()
    row.enabled = bool(enabled)


def entries(s):
    return [{"symbol": w.symbol, "exchange": w.exchange, "enabled": w.enabled, "note": w.note, "added_at": w.added_at}
            for w in s.query(Watchlist).order_by(Watchlist.added_at)]
