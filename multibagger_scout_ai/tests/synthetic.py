"""SYNTHETIC TEST DATA ONLY. Random-walk prices and invented statements. Never import this from application code."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data.connectors.base import ProviderError
from data.types import ProviderResult


def make_prices(drift=0.0008, bars=1500, seed=7, end=None):
    rng = np.random.default_rng(seed)
    end = end or pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    idx = pd.bdate_range(end=end, periods=bars)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.012, bars)))
    op = close * (1 + rng.normal(0, 0.003, bars))
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.004, bars)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.004, bars)))
    vol = rng.integers(2_000_000, 6_000_000, bars).astype(float)
    return pd.DataFrame({"Open": op, "High": hi, "Low": lo, "Close": close, "Volume": vol}, index=idx)


def make_statements():
    t = pd.Timestamp.now()
    fy0 = pd.Timestamp(year=t.year if t.month >= 5 else t.year - 1, month=3, day=31)
    cols = [fy0 - pd.DateOffset(years=i) for i in range(4)]  # latest first

    def frame(rows):
        return pd.DataFrame({c: [v[i] for v in rows.values()] for i, c in enumerate(cols)}, index=list(rows.keys()))

    return {
        "annual_income": frame({"Total Revenue": [1330, 1150, 1000, 870], "Net Income": [150, 120, 95, 80], "EBIT": [220, 180, 150, 130],
                                "Gross Profit": [500, 430, 370, 320], "Interest Expense": [10, 12, 14, 15], "Diluted EPS": [1.5, 1.2, 0.95, 0.8]}),
        "annual_balance": frame({"Total Debt": [200, 220, 240, 250], "Stockholders Equity": [900, 760, 650, 570], "Total Assets": [1500, 1300, 1150, 1000],
                                 "Current Assets": [600, 520, 450, 400], "Current Liabilities": [300, 280, 260, 240], "Ordinary Shares Number": [100, 100, 100, 100]}),
        "annual_cashflow": frame({"Operating Cash Flow": [160, 130, 100, 90], "Free Cash Flow": [100, 80, 60, 50]}),
        "quarterly_income": pd.DataFrame({pd.Timestamp(t.year, 3, 31) - pd.DateOffset(months=3 * i): [300 - 10 * i, 30 - i] for i in range(5)}, index=["Total Revenue", "Net Income"]),
    }


class FakeProvider:
    name = "SYNTHETIC_TEST"

    def __init__(self, drift=0.0008, financial=False, statements=True, seed=7, bars=1500):
        self.drift, self.financial, self.statements, self.seed, self.bars = drift, financial, statements, seed, bars

    def fetch(self, symbol, exchange="NSE"):
        h = make_prices(self.drift, self.bars, self.seed)
        px = float(h["Close"].iloc[-1])
        info = {"longName": "Synthetic Test Industries Limited", "sector": "Financial Services" if self.financial else "Industrials",
                "industry": "Synthetic", "marketCap": px * 100, "currentPrice": px, "trailingPE": 20.0, "forwardPE": 18.0, "priceToBook": 3.0,
                "enterpriseToEbitda": 12.0, "enterpriseToRevenue": 2.5, "dividendRate": 2.0, "sharesOutstanding": 100, "bookValue": 100.0,
                "heldPercentInstitutions": 0.25, "longBusinessSummary": "Synthetic company for tests."}
        return ProviderResult(provider=self.name, symbol=symbol, exchange=exchange, fetched_at=datetime.now(timezone.utc), info=info, history=h,
                              statements=make_statements() if self.statements else {}, errors={}, is_synthetic=True, note="SYNTHETIC TEST DATA")

    def fetch_history(self, symbol, exchange="NSE", period="2y"):
        return self.fetch(symbol, exchange).history.tail(500)


class DownProvider:
    name = "down_provider"

    def fetch(self, symbol, exchange="NSE"):
        raise ProviderError("simulated outage")

    def fetch_history(self, symbol, exchange="NSE", period="2y"):
        self.history_calls = getattr(self, "history_calls", 0) + 1
        raise ProviderError("simulated outage")


class FakeNews:
    def __init__(self, fail=False, items=None):
        self.fail, self.items = fail, items

    def fetch(self, query):
        if self.fail:
            raise ProviderError("simulated news outage")
        return self.items if self.items is not None else [
            {"headline": "Synthetic Test Industries bags new contract - Fake Wire", "url": "https://example.invalid/1", "published_at": "2026-11-10T08:00:00+00:00", "source": "Fake Wire"},
            {"headline": "Synthetic Test Industries bags new contract - Other Wire", "url": "https://example.invalid/2", "published_at": "2026-11-10T09:00:00+00:00", "source": "Other Wire"},
            {"headline": "Unrelated Corp shares fall", "url": "https://example.invalid/3", "published_at": "2026-11-11T09:00:00+00:00", "source": "Fake Wire"}]
