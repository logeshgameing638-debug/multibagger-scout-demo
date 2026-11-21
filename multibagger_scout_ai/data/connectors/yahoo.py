"""Yahoo Finance via yfinance (UNOFFICIAL: no SLA, may be delayed, labels/fields can change)."""
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from config import settings
from data.connectors.base import NoDataError, ProviderError
from data.types import ProviderResult

log = logging.getLogger(__name__)
SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
STATEMENTS = [
    ("annual_income", "financials"),
    ("annual_balance", "balance_sheet"),
    ("annual_cashflow", "cashflow"),
    ("quarterly_income", "quarterly_financials"),
]


class YahooConnector:
    name = "yfinance"
    description = "Yahoo Finance through yfinance (unofficial, possibly delayed)"

    def __init__(self, retries: int = 2, backoff: float = 1.5):
        self.retries, self.backoff = retries, backoff

    def _retry(self, fn, label):
        last = None
        for attempt in range(self.retries + 1):
            try:
                return fn()
            except Exception as exc:  # network, parsing, rate limit
                last = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise ProviderError(f"{label} failed after {self.retries + 1} attempts: {last}")

    def fetch_history(self, symbol: str, exchange: str = "NSE", period: str = "2y"):
        """Price history only (light scan / price checks). Raises NoDataError for empty answers."""
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError("yfinance is not installed") from exc
        ticker = yf.Ticker(symbol + SUFFIX[exchange])
        hist = self._retry(lambda: ticker.history(period=period, interval="1d", auto_adjust=False), "price history")
        if hist is None or hist.empty:
            raise NoDataError(f"no price data returned for {symbol}{SUFFIX[exchange]}")
        return hist

    def fetch(self, symbol: str, exchange: str = "NSE") -> ProviderResult:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError("yfinance is not installed") from exc
        if exchange not in SUFFIX:
            raise ProviderError(f"unsupported exchange {exchange}")
        ticker = yf.Ticker(symbol + SUFFIX[exchange])
        errors: dict = {}

        hist = self._retry(
            lambda: ticker.history(period=settings.HISTORY_PERIOD, interval="1d", auto_adjust=False), "price history")
        if hist is None or hist.empty:
            raise NoDataError(f"no price data returned for {symbol}{SUFFIX[exchange]} (unknown symbol, delisted or provider issue)")

        try:
            info = self._retry(lambda: dict(ticker.info or {}), "company info")
        except ProviderError as exc:
            info, errors["info"] = {}, str(exc)

        statements = {}
        for key, attr in STATEMENTS:
            try:
                df = self._retry(lambda a=attr: getattr(ticker, a), key)
                if df is None or df.empty:
                    errors[key] = "empty"
                    continue
                statements[key] = df.sort_index(axis=1, ascending=False)  # latest period first
            except ProviderError as exc:
                errors[key] = str(exc)

        return ProviderResult(
            provider=self.name, symbol=symbol, exchange=exchange, fetched_at=datetime.now(timezone.utc),
            info=info, history=hist, statements=statements, errors=errors,
            note="Unofficial Yahoo Finance data; may be delayed or incomplete.")
