"""Floor 01 universe: all NSE + BSE listed stocks from official lists (downloaded or imported from CSV).
NSE list URL and BSE column names could not be verified from the build sandbox; CSV import is the dependable path."""
import io
import re

import pandas as pd
import requests

from config import settings
from data.connectors.base import ProviderError
from database.models import UniverseStock
from services.clock import utc_naive

NSE_COLS = {"symbol": ["symbol"], "name": ["name of company", "company name"], "isin": ["isin number", "isin"], "series": ["series"]}
BSE_COLS = {"code": ["security code", "scrip code"], "sid": ["security id", "scrip id"], "name": ["security name", "issuer name"],
            "isin": ["isin no", "isin no.", "isin"], "series": ["group"], "status": ["status"]}
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")


def _pick(df, aliases):
    cols = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        if a in cols:
            return cols[a]
    return None


def parse(data: bytes, exchange: str):
    """Return (rows, problems). Never invents data; rows with an unusable symbol are skipped and counted."""
    df = pd.read_csv(io.BytesIO(data), dtype=str, encoding_errors="replace").dropna(how="all")
    spec = NSE_COLS if exchange == "NSE" else BSE_COLS
    col = {k: _pick(df, v) for k, v in spec.items()}
    need = "symbol" if exchange == "NSE" else "code"
    if col[need] is None:
        raise ValueError(f"{exchange} CSV: required column for symbol/code not found (columns: {list(df.columns)[:8]})")
    rows, bad = [], 0
    g = lambda r, k: (str(r[col[k]]).strip() if col.get(k) is not None and pd.notna(r[col[k]]) else None)
    for _, r in df.iterrows():
        sym = (g(r, need) or "").upper()
        if not CODE_RE.match(sym):
            bad += 1
            continue
        rows.append({"exchange": exchange, "symbol": sym, "alt_symbol": g(r, "sid") if exchange == "BSE" else None, "name": g(r, "name"),
                     "isin": g(r, "isin"), "series": g(r, "series"), "listing_status": (g(r, "status") or "Active") if exchange == "BSE" else "Active"})
    return rows, ([f"{bad} rows skipped (invalid symbol/code)"] if bad else [])


def import_rows(s, rows, source):
    have = {(u.exchange, u.symbol): u for u in s.query(UniverseStock).filter(UniverseStock.exchange.in_({r["exchange"] for r in rows}))} if rows else {}
    ins = upd = 0
    for r in rows:
        u = have.get((r["exchange"], r["symbol"]))
        if u is None:
            s.add(UniverseStock(source=source, **r))
            ins += 1
        else:
            for k, v in r.items():
                if v is not None:
                    setattr(u, k, v)
            u.source, u.imported_at = source, utc_naive()
            upd += 1
    return {"inserted": ins, "updated": upd}


def import_csv(s, data: bytes, exchange: str, source: str):
    rows, problems = parse(data, exchange)
    return {**import_rows(s, rows, source), "rows_read": len(rows), "problems": problems}


def download_nse():
    try:
        r = requests.get(settings.NSE_EQUITY_LIST_URL, timeout=settings.HTTP_TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; MultibaggerScoutAI/0.1)", "Accept": "text/csv,*/*"})
        r.raise_for_status()
        return r.content
    except Exception as exc:
        raise ProviderError(f"NSE equity list download failed: {exc}") from exc


def scan_list(s, exchange=None):
    """Active stocks to scan. A BSE listing whose ISIN also trades on NSE is skipped (same company; NSE data preferred)."""
    q = s.query(UniverseStock)
    rows = [u for u in q.order_by(UniverseStock.exchange, UniverseStock.symbol) if (u.listing_status or "Active").lower() == "active"]
    nse_isins = {u.isin for u in rows if u.exchange == "NSE" and u.isin}
    out = [{"exchange": u.exchange, "symbol": u.symbol, "name": u.name} for u in rows
           if not (u.exchange == "BSE" and u.isin and u.isin in nse_isins)]
    return [x for x in out if exchange in (None, x["exchange"])]


def counts(s):
    n = lambda ex: s.query(UniverseStock).filter_by(exchange=ex).count()
    return {"NSE": n("NSE"), "BSE": n("BSE"), "to_scan": len(scan_list(s))}
