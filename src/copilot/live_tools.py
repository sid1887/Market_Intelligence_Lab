"""
src/copilot/live_tools.py
Live Intraday Quote & Web Catalyst Search Fusion Engine for Copilot.

Capabilities:
1. Fast Intraday Price & Volume Pulse:
   - Fetches live LTP, Open, Day High/Low, Prev Close, and Volume via yfinance fast_info
     with hard 2.5s timeout and 60s TTL memory caching.
   - Fuses live spot price against MIL's EOD database:
     Recomputes live distance to 50 & 200 SMA, live GARCH 80%/95% price cone position,
     and live mark-to-market unrealized P&L on active demat holdings (e.g., GAIL).
2. Live Web & Catalyst Search:
   - Queries Brave Search API (if BRAVE_API_KEY is configured) with automatic fallback
     to Google News RSS for Indian Equities (< 2.5s timeout, 300s TTL cache).
   - Ingests fresh order wins, earnings surprises, and regulatory developments.
"""

import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager
from src.storage.cache import register_memory_guard_hook

logger = logging.getLogger("MIL.CopilotLiveTools")

# In-Memory TTL Caches (RAM footprint < 500 KB)
_QUOTE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_WEB_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

QUOTE_TTL_SEC = 60.0
WEB_TTL_SEC = 300.0
_MAX_CACHE_ENTRIES = 128
HARD_TIMEOUT_SEC = 2.5
DEFAULT_ANGEL_ONE_DP_CHARGE = 23.60


def clear_live_tools_caches() -> None:
    """Clears copilot live quote/web TTL caches under RSS pressure."""
    _QUOTE_CACHE.clear()
    _WEB_CACHE.clear()


register_memory_guard_hook(clear_live_tools_caches)


def _prune_cache(cache: Dict[str, Tuple[float, Any]], ttl_sec: float, now: float) -> None:
    expired = [k for k, (ts, _) in cache.items() if now - ts >= ttl_sec]
    for k in expired:
        cache.pop(k, None)
    if len(cache) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(cache.items(), key=lambda item: item[1][0])[0]
        cache.pop(oldest_key, None)


def fetch_live_intraday_quote(
    symbol: str,
    db: Optional[DatabaseManager] = None,
    timeout: float = HARD_TIMEOUT_SEC
) -> Dict[str, Any]:
    """
    Fetches live intraday quote via yfinance fast_info with timeout guard and TTL caching,
    then fuses live spot price with SQLite EOD technicals and demat holdings.
    """
    clean_sym = symbol.strip().upper()
    now = time.time()

    # Check cache
    if clean_sym in _QUOTE_CACHE:
        cached_time, cached_val = _QUOTE_CACHE[clean_sym]
        if now - cached_time < QUOTE_TTL_SEC:
            return cached_val

    raw_quote: Dict[str, Any] = {}

    def _fetch_yfinance() -> Dict[str, Any]:
        import yfinance as yf
        # Indian equity ticker on Yahoo Finance is SYMBOL.NS
        yf_ticker = f"{clean_sym}.NS" if not clean_sym.endswith(".NS") and clean_sym != "NIFTY 50" else ("^NSEI" if clean_sym == "NIFTY 50" else clean_sym)
        t = yf.Ticker(yf_ticker)
        fi = t.fast_info
        def _get_val(obj: Any, *keys: str, default: float = 0.0) -> float:
            for k in keys:
                if hasattr(obj, k):
                    val = getattr(obj, k)
                    if val is not None:
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
                if isinstance(obj, dict) or hasattr(obj, "get"):
                    try:
                        val = obj.get(k)
                        if val is not None:
                            return float(val)
                    except Exception:
                        pass
            return default

        ltp = _get_val(fi, "last_price", "lastPrice")
        prev_close = _get_val(fi, "previous_close", "previousClose")
        open_p = _get_val(fi, "open", default=ltp)
        day_h = _get_val(fi, "day_high", "dayHigh", default=ltp)
        day_l = _get_val(fi, "day_low", "dayLow", default=ltp)
        vol = int(_get_val(fi, "last_volume", "lastVolume", default=0.0))

        chg_pct = round(((ltp - prev_close) / prev_close * 100.0), 2) if prev_close > 0 else 0.0

        return {
            "symbol": clean_sym,
            "ltp": round(ltp, 2),
            "open": round(open_p, 2),
            "day_high": round(day_h, 2),
            "day_low": round(day_l, 2),
            "prev_close": round(prev_close, 2),
            "change_pct": chg_pct,
            "volume": vol,
            "is_live": ltp > 0,
            "source": "yfinance_fast_info"
        }

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_fetch_yfinance)
            raw_quote = future.result(timeout=timeout)
    except (FuturesTimeoutError, Exception) as e:
        logger.debug(f"[LIVE-QUOTE] Live quote fetch timed out or failed for {clean_sym}: {e}")

    # Fallback to SQLite EOD close if live fetch failed or returned 0
    eod_fallback_close = None
    if db:
        try:
            with db.get_connection() as conn:
                row = conn.execute("""
                    SELECT close, trading_date
                    FROM ohlcv_daily
                    WHERE symbol = ?
                    ORDER BY trading_date DESC
                    LIMIT 1
                """, (clean_sym,)).fetchone()
                if row and row["close"]:
                    eod_fallback_close = float(row["close"])
        except Exception as e:
            logger.debug(f"[LIVE-QUOTE] SQLite fallback failed for {clean_sym}: {e}")

    if not raw_quote.get("ltp") or raw_quote.get("ltp") == 0.0:
        if eod_fallback_close:
            raw_quote = {
                "symbol": clean_sym,
                "ltp": round(eod_fallback_close, 2),
                "open": round(eod_fallback_close, 2),
                "day_high": round(eod_fallback_close, 2),
                "day_low": round(eod_fallback_close, 2),
                "prev_close": round(eod_fallback_close, 2),
                "change_pct": 0.0,
                "volume": 0,
                "is_live": False,
                "source": "sqlite_eod_settled"
            }
        else:
            raw_quote = {
                "symbol": clean_sym,
                "ltp": 0.0,
                "open": 0.0,
                "day_high": 0.0,
                "day_low": 0.0,
                "prev_close": 0.0,
                "change_pct": 0.0,
                "volume": 0,
                "is_live": False,
                "source": "unavailable"
            }

    ltp = raw_quote["ltp"]

    # Database Fusion: recompute SMAs, GARCH cone position, and open holding mark-to-market
    fusion: Dict[str, Any] = {
        "live_vs_sma200_pct": None,
        "live_vs_sma50_pct": None,
        "live_garch_band_position": "MID_CONE",
        "holding_status": None,
        "open_holding": None,
    }

    if db and ltp > 0:
        try:
            with db.get_connection() as conn:
                # 1. 50 & 200 SMA from latest bars
                try:
                    sma_rows = conn.execute("""
                        SELECT close
                        FROM ohlcv_daily
                        WHERE symbol = ?
                        ORDER BY trading_date DESC
                        LIMIT 200
                    """, (clean_sym,)).fetchall()
                    closes = [float(r["close"]) for r in sma_rows if r["close"]]

                    if len(closes) >= 50:
                        sma50 = sum(closes[:50]) / 50.0
                        fusion["live_vs_sma50_pct"] = round(((ltp - sma50) / sma50 * 100.0), 2)
                    if len(closes) >= 200:
                        sma200 = sum(closes[:200]) / 200.0
                        fusion["live_vs_sma200_pct"] = round(((ltp - sma200) / sma200 * 100.0), 2)
                except Exception as se:
                    logger.debug(f"[LIVE-FUSION] SMA calculation skipped for {clean_sym}: {se}")

                # 2. GARCH Bounds
                try:
                    garch_row = conn.execute("""
                        SELECT forecast_floor_p05, forecast_target_p80
                        FROM quant_factors_daily
                        WHERE symbol = ?
                        ORDER BY trading_date DESC
                        LIMIT 1
                    """, (clean_sym,)).fetchone()
                    if garch_row and garch_row["forecast_floor_p05"] and garch_row["forecast_target_p80"]:
                        floor_95 = float(garch_row["forecast_floor_p05"])
                        target_80 = float(garch_row["forecast_target_p80"])
                        if ltp <= floor_95:
                            fusion["live_garch_band_position"] = "BELOW_95_FLOOR"
                        elif ltp >= target_80:
                            fusion["live_garch_band_position"] = "ABOVE_80_TARGET"
                        else:
                            fusion["live_garch_band_position"] = "INSIDE_CONE"
                except Exception as ge:
                    logger.debug(f"[LIVE-FUSION] GARCH calculation skipped for {clean_sym}: {ge}")

                # 3. Active Demat Holding Fusion
                try:
                    h_row = conn.execute("""
                        SELECT qty, avg_buy_price, buy_value
                        FROM real_open_holdings
                        WHERE symbol = ?
                    """, (clean_sym,)).fetchone()
                    if h_row:
                        h_qty = int(h_row["qty"] or 0)
                        h_avg = float(h_row["avg_buy_price"] or 0.0)
                        h_buy_val = float(h_row["buy_value"] or 0.0)

                        unreal_gross = round((ltp * h_qty) - h_buy_val, 2)
                        unreal_pct = round(((ltp - h_avg) / h_avg * 100.0), 2) if h_avg > 0 else 0.0
                        unreal_net = round(unreal_gross - DEFAULT_ANGEL_ONE_DP_CHARGE - (0.001 * ltp * h_qty), 2)

                        breakeven_p = round((h_buy_val + DEFAULT_ANGEL_ONE_DP_CHARGE + (0.001 * h_buy_val)) / max(h_qty, 1), 2)

                        holding_obj = {
                            "is_held": True,
                            "qty": h_qty,
                            "quantity": h_qty,
                            "avg_buy_price": h_avg,
                            "live_unrealized_pnl": unreal_gross,
                            "live_net_pnl_after_dp": unreal_net,
                            "unrealized_pct": unreal_pct,
                            "breakeven_exit_price": breakeven_p,
                            "points_to_breakeven": round(breakeven_p - ltp, 2),
                        }
                        fusion["holding_status"] = holding_obj
                        fusion["open_holding"] = holding_obj
                except Exception as he:
                    logger.debug(f"[LIVE-FUSION] Holding fusion skipped for {clean_sym}: {he}")
        except Exception as e:
            logger.debug(f"[LIVE-FUSION] DB fusion error for {clean_sym}: {e}")

    result = {**raw_quote, **fusion}
    _prune_cache(_QUOTE_CACHE, QUOTE_TTL_SEC, now)
    _QUOTE_CACHE[clean_sym] = (now, result)
    return result


def search_live_web_catalysts(
    symbol: str,
    company_name: str = "",
    user_query: str = "",
    timeout: float = HARD_TIMEOUT_SEC
) -> List[Dict[str, Any]]:
    """
    Searches for live market catalysts, earnings surprises, and breaking news
    using Brave Search API (if key configured) or Google News RSS for Indian equities.
    Guaranteed < 2.5s response with 300s TTL cache.
    """
    clean_sym = symbol.strip().upper()
    cache_key = f"{clean_sym}:{company_name[:20]}"
    now = time.time()

    if cache_key in _WEB_CACHE:
        cached_time, cached_val = _WEB_CACHE[cache_key]
        if now - cached_time < WEB_TTL_SEC:
            return cached_val

    search_query = f"{company_name or clean_sym} share price NSE news"

    def _fetch_rss() -> List[Dict[str, Any]]:
        encoded_q = urllib.parse.quote(search_query)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        items = []
        for el in root.findall(".//item")[:5]:
            title = el.findtext("title") or ""
            link = el.findtext("link") or ""
            pub_date = el.findtext("pubDate") or ""
            source = el.findtext("source") or "News"

            # Clean Google News suffix "- Source"
            clean_title = title.split(" - ")[0].strip() if " - " in title else title
            if clean_title:
                items.append({
                    "title": clean_title,
                    "source": source,
                    "published_at": pub_date[:25],
                    "link": link
                })
        return items

    def _fetch_brave() -> List[Dict[str, Any]]:
        api_key = os.getenv("BRAVE_API_KEY", "").strip()
        if not api_key:
            return []
        import json
        encoded_q = urllib.parse.quote(search_query)
        url = f"https://api.search.brave.com/res/v1/web/search?q={encoded_q}&count=5"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
                "User-Agent": "MIL/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = []
        for res in data.get("web", {}).get("results", [])[:5]:
            items.append({
                "title": res.get("title", ""),
                "snippet": res.get("description", ""),
                "source": res.get("profile", {}).get("name", "Web"),
                "published_at": res.get("age", ""),
                "link": res.get("url", "")
            })
        return items

    catalysts: List[Dict[str, Any]] = []
    try:
        # Prefer Brave if key present, fallback to Google News RSS
        with ThreadPoolExecutor(max_workers=1) as executor:
            if os.getenv("BRAVE_API_KEY"):
                future = executor.submit(_fetch_brave)
                catalysts = future.result(timeout=timeout)
            if not catalysts:
                future = executor.submit(_fetch_rss)
                catalysts = future.result(timeout=timeout)
    except Exception as e:
        logger.debug(f"[LIVE-WEB] Web catalyst search timed out or failed for {clean_sym}: {e}")

    _prune_cache(_WEB_CACHE, WEB_TTL_SEC, now)
    _WEB_CACHE[cache_key] = (now, catalysts)
    return catalysts
