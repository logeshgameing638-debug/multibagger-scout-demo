from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd


@dataclass
class ProviderResult:
    """Raw data bundle from one provider. `errors` lists sub-requests that failed (partial data)."""
    provider: str
    symbol: str
    exchange: str
    fetched_at: datetime
    info: dict
    history: pd.DataFrame
    statements: dict = field(default_factory=dict)  # annual_income/annual_balance/annual_cashflow/quarterly_income
    errors: dict = field(default_factory=dict)
    is_synthetic: bool = False
    note: str = ""
