from typing import List, Dict, Any, Optional, Set
from src.storage.database import DatabaseManager
from src.quant.benchmark import calculate_split_bonus_adjustment_factors

class MarketBreadthEngine:
    """
    Computes deterministic market breadth metrics for index constituents on a given trading session.
    Enforces strict point-in-time constituent lookup, explicit data coverage accounting,
    split/bonus adjusted SMA evaluations, and warm-up window restrictions.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def compute_daily_breadth(
        self,
        as_of_date: str,
        index_name: str = "NIFTY 50"
    ) -> Dict[str, Any]:
        """
        Calculates market breadth for the specified index on as_of_date.
        Reports:
        - Point-in-time constituent metadata and survivorship status
        - Exact coverage statistics (expected, valid, missing, coverage %)
        - Advance / Decline / Unchanged stock counts and volume breakdown
        - Percent of constituents above 20, 50, and 200-day SMAs with eligibility tracking
        """
        # 1. Point-in-time constituent lookup
        constituent_info = self.db.get_index_constituents(index_name, as_of_date)
        expected_symbols = set(constituent_info["constituents"])
        expected_count = len(expected_symbols)

        if expected_count == 0:
            return {
                "as_of_date": as_of_date,
                "index_name": index_name,
                "error": f"No constituents indexed for {index_name} on {as_of_date}.",
                "expected_count": 0,
                "valid_count": 0,
                "coverage_pct": 0.0
            }

        # 2. Retrieve today's settled records for the universe
        # Query ohlcv_daily for as_of_date
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ohlcv_daily WHERE trading_date = ? AND series = 'EQ'",
                (as_of_date,)
            )
            today_records = [dict(r) for r in cursor.fetchall()]

        records_by_symbol = {r["symbol"]: r for r in today_records if r["symbol"] in expected_symbols}
        valid_symbols = set(records_by_symbol.keys())
        missing_symbols = sorted(list(expected_symbols - valid_symbols))

        valid_count = len(valid_symbols)
        missing_count = len(missing_symbols)
        coverage_pct = (valid_count / expected_count) * 100.0 if expected_count > 0 else 0.0

        # 3. Advance / Decline / Volume Breadth
        advances = 0
        declines = 0
        unchanged = 0
        adv_vol = 0
        dec_vol = 0
        unch_vol = 0

        advancing_symbols = []
        declining_symbols = []
        unchanged_symbols = []

        for sym, r in records_by_symbol.items():
            close_p = float(r["close"])
            prev_p = float(r["prev_close"]) if r.get("prev_close") is not None else None
            vol = int(r.get("volume", 0))

            if prev_p is None:
                # If prev_close is missing from bar, look up previous close from history
                prev_hist = self.db.get_stock_history(sym, start_date=None, end_date=as_of_date)
                if len(prev_hist) >= 2:
                    prev_p = float(prev_hist[-2]["close"])

            if prev_p is not None:
                if close_p > prev_p:
                    advances += 1
                    adv_vol += vol
                    advancing_symbols.append(sym)
                elif close_p < prev_p:
                    declines += 1
                    dec_vol += vol
                    declining_symbols.append(sym)
                else:
                    unchanged += 1
                    unch_vol += vol
                    unchanged_symbols.append(sym)
            else:
                unchanged += 1
                unch_vol += vol
                unchanged_symbols.append(sym)

        vol_breadth_ratio = (adv_vol / dec_vol) if dec_vol > 0 else (float("inf") if adv_vol > 0 else 1.0)
        total_vol = adv_vol + dec_vol + unch_vol
        advance_volume_share = (adv_vol / total_vol * 100.0) if total_vol > 0 else 0.0

        # 4. Moving Average Breadth (% above SMA 20, 50, 200)
        # Corporate action adjusted price series must be used to prevent split/bonus artifacts
        above_20 = 0
        eligible_20 = 0
        above_50 = 0
        eligible_50 = 0
        above_200 = 0
        eligible_200 = 0

        for sym in valid_symbols:
            hist = self.db.get_stock_history(sym, start_date=None, end_date=as_of_date)
            if not hist:
                continue

            cas = self.db.get_corporate_actions(sym)
            adj_hist = calculate_split_bonus_adjustment_factors(hist, cas)
            n_hist = len(adj_hist)
            today_adj_close = adj_hist[-1]["adjusted_close"]

            # SMA 20
            if n_hist >= 20:
                eligible_20 += 1
                sma20 = sum(r["adjusted_close"] for r in adj_hist[-20:]) / 20.0
                if today_adj_close > sma20:
                    above_20 += 1

            # SMA 50
            if n_hist >= 50:
                eligible_50 += 1
                sma50 = sum(r["adjusted_close"] for r in adj_hist[-50:]) / 50.0
                if today_adj_close > sma50:
                    above_50 += 1

            # SMA 200
            if n_hist >= 200:
                eligible_200 += 1
                sma200 = sum(r["adjusted_close"] for r in adj_hist[-200:]) / 200.0
                if today_adj_close > sma200:
                    above_200 += 1

        pct_above_20 = (above_20 / eligible_20 * 100.0) if eligible_20 > 0 else None
        pct_above_50 = (above_50 / eligible_50 * 100.0) if eligible_50 > 0 else None
        pct_above_200 = (above_200 / eligible_200 * 100.0) if eligible_200 > 0 else None

        return {
            "as_of_date": as_of_date,
            "index_name": index_name,
            # Point-in-time constituent provenance
            "is_survivorship_bias_free": constituent_info["is_survivorship_bias_free"],
            "membership_basis": constituent_info["membership_basis"],
            "membership_warning": constituent_info.get("warning"),
            # Explicit coverage tracking (Mandatory Condition 5)
            "expected_constituents_count": expected_count,
            "valid_observations_count": valid_count,
            "missing_observations_count": missing_count,
            "missing_symbols": missing_symbols,
            "coverage_pct": round(coverage_pct, 2),
            # Advance / Decline Statistics
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "ad_ratio": round(advances / declines, 3) if declines > 0 else None,
            "advance_volume": adv_vol,
            "decline_volume": dec_vol,
            "unchanged_volume": unch_vol,
            "total_volume": total_vol,
            "volume_breadth_ratio": round(vol_breadth_ratio, 3) if vol_breadth_ratio != float("inf") else 999.0,
            "advance_volume_share_pct": round(advance_volume_share, 2),
            # Moving Average Breadth with Eligibility Tracking (Mandatory Condition 1)
            "sma20": {
                "eligible_count": eligible_20,
                "above_count": above_20,
                "pct_above": round(pct_above_20, 2) if pct_above_20 is not None else None,
                "is_warmup": eligible_20 < valid_count
            },
            "sma50": {
                "eligible_count": eligible_50,
                "above_count": above_50,
                "pct_above": round(pct_above_50, 2) if pct_above_50 is not None else None,
                "is_warmup": eligible_50 < valid_count
            },
            "sma200": {
                "eligible_count": eligible_200,
                "above_count": above_200,
                "pct_above": round(pct_above_200, 2) if pct_above_200 is not None else None,
                "is_warmup": eligible_200 < valid_count
            }
        }
