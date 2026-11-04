"""
Market Intelligence Lab — API Serialization Utilities (Milestone B6.4.1).

Provides robust recursive serialization sanitizers to prevent Starlette/FastAPI
`ValueError: Out of range float values are not JSON compliant: nan` crashes
when returning indicators, ratios, or DataFrames with missing data or division by zero.
"""

import os
import math
import sqlite3
from typing import Any, Optional
import numpy as np
import pandas as pd


DATABASE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "market_lab.db")
)


def get_db_connection():
    """
    Dependency that provides a safe read-only SQLite connection configured for concurrent WAL reads.
    Does not block concurrent writes or reader transactions.
    """
    db_uri = f"file:{DATABASE_PATH}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def safe_float(val: Any, precision: Optional[int] = None) -> Optional[float]:
    """
    Safely converts a value to float and handles None, NaN, Inf, and pd.NA.
    Optionally rounds to specified precision. Returns None if invalid.
    """
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, precision) if precision is not None else f
    except (ValueError, TypeError):
        return None


def safe_int(val: Any) -> Optional[int]:
    """
    Safely converts a value to integer, handling None, NaN, and pd.NA.
    """
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (ValueError, TypeError):
        return None


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively traverses dicts, lists, tuples, sets, and scalars,
    replacing any NaN, Infinity, -Infinity, or pd.NA with None (which serializes as JSON null).
    Handles Pandas DataFrames and Series safely without throwing JSON compliance errors.
    """
    if obj is None:
        return None

    # Handle Pandas DataFrames: convert with .where(pd.notnull(df), None) as specified
    if isinstance(obj, pd.DataFrame):
        df_clean = obj.where(pd.notnull(obj), None)
        return sanitize_for_json(df_clean.to_dict(orient="records"))

    # Handle Pandas Series
    if isinstance(obj, pd.Series):
        s_clean = obj.where(pd.notnull(obj), None)
        return sanitize_for_json(s_clean.to_dict())

    # Handle Floats and Numpy Floats
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)

    # Handle Integers and Numpy Integers
    if isinstance(obj, (int, np.integer)):
        return int(obj)

    # Handle Booleans and Numpy Booleans
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)

    # Handle Dictionaries
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}

    # Handle Lists, Tuples, and Sets
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]

    # Catch any pandas NA / NaT types
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    return obj
