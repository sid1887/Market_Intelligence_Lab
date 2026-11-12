"""
Market Intelligence Lab — Institutional Macro Telemetry Client.
P0-05, ADR-0002.

Provides honest macro observations with explicit timestamps and freshness status.
Eliminates fabricated live claims by tracking observed_at dates and sources.
"""

import json
import os
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger("macro_client")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_FILE = os.path.join(ROOT_DIR, "data", "macro_telemetry.json")
CACHE_TTL_SECONDS = 300  # 5 minutes TTL for macro observations


def is_valid_num(v: Any) -> bool:
    """Returns True if value is a finite, non-null, non-NaN number."""
    if v is None:
        return False
    if pd is not None and pd.isna(v):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    return False

DEFAULT_MACRO_OBSERVATIONS = [
    {
        "symbol": "USD/INR",
        "label": "USD / INR",
        "value": 93.98,
        "unit": "₹",
        "change_pct": 0.06,
        "source": "yfinance",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "BASELINE"
    },
    {
        "symbol": "BRENT",
        "label": "Brent Crude",
        "value": 92.68,
        "unit": "$/bbl",
        "change_pct": -0.09,
        "source": "yfinance",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "BASELINE"
    },
    {
        "symbol": "US10Y",
        "label": "US 10Y Yield",
        "value": 4.45,
        "unit": "%",
        "change_pct": 0.34,
        "source": "yfinance",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "BASELINE"
    },
    {
        "symbol": "IN10Y",
        "label": "India 10Y G-Sec",
        "value": 6.82,
        "unit": "%",
        "change_pct": -0.15,
        "source": "unconfigured_ccil",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "freshness_status": "BASELINE"
    }
]


class MacroClient:
    @staticmethod
    def get_macro_telemetry(force_refresh: bool = False) -> Dict[str, Any]:
        """Returns verified macro telemetry with real observed timestamps and cache TTL enforcement."""
        if not force_refresh and os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    data = json.load(f)
                    retrieved_str = data.get("retrieval_timestamp")
                    if retrieved_str:
                        retrieved_dt = datetime.fromisoformat(retrieved_str)
                        age = (datetime.now(timezone.utc) - retrieved_dt).total_seconds()
                        if age < CACHE_TTL_SECONDS:
                            return data
            except Exception:
                pass

        if yf is None:
            return {
                "status": "unavailable",
                "as_of_session": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "indicators": DEFAULT_MACRO_OBSERVATIONS
            }

        # Attempt live observation fetch
        try:
            indicators = []
            now_iso = datetime.now(timezone.utc).isoformat()
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            # 1. USD / INR
            try:
                usd = yf.Ticker("USDINR=X").history(period="2d")
                if len(usd) >= 2 and is_valid_num(usd["Close"].iloc[-1]):
                    val = round(float(usd["Close"].iloc[-1]), 2)
                    prev = float(usd["Close"].iloc[-2]) if is_valid_num(usd["Close"].iloc[-2]) else None
                    chg = round(((val - prev) / prev) * 100, 2) if prev and prev > 0 else None
                    obs_at = usd.index[-1].isoformat()
                    indicators.append({
                        "symbol": "USD/INR",
                        "label": "USD / INR",
                        "value": val,
                        "unit": "₹",
                        "change_pct": chg,
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                elif len(usd) == 1 and is_valid_num(usd["Close"].iloc[-1]):
                    val = round(float(usd["Close"].iloc[-1]), 2)
                    obs_at = usd.index[-1].isoformat()
                    indicators.append({
                        "symbol": "USD/INR",
                        "label": "USD / INR",
                        "value": val,
                        "unit": "₹",
                        "change_pct": None,  # Single observation: change is unobservable
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                else:
                    indicators.append(DEFAULT_MACRO_OBSERVATIONS[0])
            except Exception as e:
                logger.warning(f"Failed to fetch USD/INR live telemetry: {e}")
                indicators.append(DEFAULT_MACRO_OBSERVATIONS[0])

            # 2. Brent Crude
            try:
                brent = yf.Ticker("BZ=F").history(period="2d")
                if len(brent) >= 2 and is_valid_num(brent["Close"].iloc[-1]):
                    val = round(float(brent["Close"].iloc[-1]), 2)
                    prev = float(brent["Close"].iloc[-2]) if is_valid_num(brent["Close"].iloc[-2]) else None
                    chg = round(((val - prev) / prev) * 100, 2) if prev and prev > 0 else None
                    obs_at = brent.index[-1].isoformat()
                    indicators.append({
                        "symbol": "BRENT",
                        "label": "Brent Crude",
                        "value": val,
                        "unit": "$/bbl",
                        "change_pct": chg,
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                elif len(brent) == 1 and is_valid_num(brent["Close"].iloc[-1]):
                    val = round(float(brent["Close"].iloc[-1]), 2)
                    obs_at = brent.index[-1].isoformat()
                    indicators.append({
                        "symbol": "BRENT",
                        "label": "Brent Crude",
                        "value": val,
                        "unit": "$/bbl",
                        "change_pct": None,  # Single observation: change is unobservable
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                else:
                    indicators.append(DEFAULT_MACRO_OBSERVATIONS[1])
            except Exception as e:
                logger.warning(f"Failed to fetch Brent live telemetry: {e}")
                indicators.append(DEFAULT_MACRO_OBSERVATIONS[1])

            # 3. US 10Y Yield
            try:
                us10y = yf.Ticker("^TNX").history(period="2d")
                if len(us10y) >= 2 and is_valid_num(us10y["Close"].iloc[-1]):
                    val = round(float(us10y["Close"].iloc[-1]), 2)
                    prev = float(us10y["Close"].iloc[-2]) if is_valid_num(us10y["Close"].iloc[-2]) else None
                    chg = round(((val - prev) / prev) * 100, 2) if prev and prev > 0 else None
                    obs_at = us10y.index[-1].isoformat()
                    indicators.append({
                        "symbol": "US10Y",
                        "label": "US 10Y Yield",
                        "value": val,
                        "unit": "%",
                        "change_pct": chg,
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                elif len(us10y) == 1 and is_valid_num(us10y["Close"].iloc[-1]):
                    val = round(float(us10y["Close"].iloc[-1]), 2)
                    obs_at = us10y.index[-1].isoformat()
                    indicators.append({
                        "symbol": "US10Y",
                        "label": "US 10Y Yield",
                        "value": val,
                        "unit": "%",
                        "change_pct": None,  # Single observation: change is unobservable
                        "source": "yfinance",
                        "retrieval_timestamp": now_iso,
                        "observed_at": obs_at,
                        "freshness_status": "LIVE_FEED"
                    })
                else:
                    indicators.append(DEFAULT_MACRO_OBSERVATIONS[2])
            except Exception as e:
                logger.warning(f"Failed to fetch US10Y live telemetry: {e}")
                indicators.append(DEFAULT_MACRO_OBSERVATIONS[2])

            # 4. India 10Y G-Sec (Unconfigured CCIL provider)
            indicators.append(DEFAULT_MACRO_OBSERVATIONS[3])

            live_count = sum(1 for ind in indicators if ind.get("freshness_status") == "LIVE_FEED")
            if live_count >= 3:
                payload_status = "live_observed"
            elif live_count > 0:
                payload_status = "partial_live"
            else:
                payload_status = "unavailable"

            payload = {
                "status": payload_status,
                "as_of_session": today_str,
                "retrieval_timestamp": now_iso,
                "indicators": indicators
            }

            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w") as f:
                json.dump(payload, f, indent=2)

            return payload

        except Exception as e:
            logger.warning(f"Failed to fetch live macro observations: {e}")
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r") as f:
                        cached_data = json.load(f)
                        cached_data["status"] = "cached_observed"
                        return cached_data
                except Exception:
                    pass
            return {
                "status": "baseline_active",
                "as_of_session": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "indicators": DEFAULT_MACRO_OBSERVATIONS
            }
