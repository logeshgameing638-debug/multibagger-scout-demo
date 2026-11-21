import math
from datetime import date, datetime

import numpy as np
import pandas as pd


def to_jsonable(o):
    """Recursively convert numpy/pandas/datetime values to JSON-safe types. Keys starting with '_' are dropped."""
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple, set)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, (pd.DataFrame, pd.Series)):
        return None
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, (datetime, date, pd.Timestamp)):
        return o.isoformat()
    return o
