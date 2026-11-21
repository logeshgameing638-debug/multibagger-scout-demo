from typing import Protocol
from data.types import ProviderResult


class ProviderError(Exception):
    """Raised when a provider cannot return usable data."""


class NoDataError(ProviderError):
    """Provider answered but has no data for this symbol (unknown, delisted, suspended). Not a transient failure."""


class MarketDataProvider(Protocol):
    name: str

    def fetch(self, symbol: str, exchange: str) -> ProviderResult: ...

    def fetch_history(self, symbol: str, exchange: str, period: str = "2y"): ...
