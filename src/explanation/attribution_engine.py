"""
Market Intelligence Lab: Generalized Movement Attribution & Automated Event Studies.

Provides:
- Anomaly scanner across universe instruments (volume spikes & volatility-scaled return shocks).
- Mathematically conserved three-tier return decomposition:
  Total Return = Market Component + Sector Component + Idiosyncratic Residual.
- Corporate disclosure proximity correlation with automated OLS event study evaluation (CAR[-1, +1]).
- Non-causal classification taxonomy and provenance linking.
"""

import math
import datetime
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple, Set

from src.storage.database import DatabaseManager
from src.quant.event_study import EventStudyEngine
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.evidence.constants import (
    resolve_sector_benchmark,
    SectorBenchmarkType,
    DATA_GOVERNANCE_NOTICE
)


@dataclass
class AttributionResult:
    """
    Encapsulates the mathematical decomposition and empirical attribution for a single session.
    Guarantees: Total Return = Market Component + Sector Component + Idiosyncratic Residual.
    """
    symbol: str
    trading_date: str
    total_return: float
    market_component: float
    sector_component: float
    residual: float
    expected_return: float
    beta_nifty: float
    market_return: float
    beta_sector: float
    sector_return: float
    sector_name: str
    anomaly_triggers: List[str]
    has_correlated_disclosure: bool
    correlated_disclosure: Optional[Dict[str, Any]]
    car_minus1_plus1: Optional[float]
    attribution_tag: str
    explanation_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MovementAttributionEngine:
    """
    Generalized econometric movement attribution engine.
    Scans, decomposes, and correlates price and volume anomalies across all instruments.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.event_study_engine = EventStudyEngine(db)
        self.movement_analyzer = MarketMovementAnalyzer(db)
        self._calendar_dates_cache: Optional[List[str]] = None

    def get_trading_calendar(self) -> List[str]:
        """Returns sorted list of authoritative trading calendar dates from authentic equity trading bars."""
        if self._calendar_dates_cache is None:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT DISTINCT trading_date FROM ohlcv_daily WHERE series = 'EQ' AND COALESCE(is_synthetic, 0) = 0 ORDER BY trading_date ASC"
                )
                self._calendar_dates_cache = [r[0] for r in cur.fetchall()]
        return self._calendar_dates_cache

    @staticmethod
    def align_disclosure_timestamp(
        broadcast_timestamp_ist: str,
        trading_calendar_dates: List[str]
    ) -> str:
        """
        Aligns disclosure timestamp to effective trading session t=0.
        Announcements made after 15:30:00 IST or on non-trading days shift to the next trading day.
        """
        return EventStudyEngine.align_disclosure_to_trading_session(
            broadcast_timestamp_ist=broadcast_timestamp_ist,
            trading_calendar_dates=trading_calendar_dates
        )

    def scan_anomalies(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        lookback_sessions: Optional[int] = 30
    ) -> List[Dict[str, Any]]:
        """
        Queries quant_factors_daily for sessions where:
        1. is_volume_spike_zscore == 1, OR
        2. Absolute 1-day return exceeds 2.5 * trailing 20-day daily volatility (volatility_annualized / sqrt(252)).
        """
        calendar = self.get_trading_calendar()
        if not calendar:
            return []

        if lookback_sessions and not start_date and not end_date:
            target_dates = calendar[-lookback_sessions:]
            min_date = target_dates[0]
            max_date = target_dates[-1]
        else:
            min_date = start_date or calendar[0]
            max_date = end_date or calendar[-1]

        with self.db.get_connection() as conn:
            sql = """
            SELECT 
                q.symbol,
                q.trading_date,
                q.ret_1d,
                q.volatility_annualized,
                q.volume_zscore_50d,
                q.is_volume_spike_zscore,
                q.beta_60d_nifty
            FROM quant_factors_daily q
            WHERE q.trading_date BETWEEN ? AND ?
            """
            params: List[Any] = [min_date, max_date]
            if symbol:
                sql += " AND q.symbol = ?"
                params.append(symbol)

            sql += " ORDER BY q.trading_date DESC, q.symbol ASC;"
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]

        anomalies = []
        for r in rows:
            triggers = []
            if r.get("is_volume_spike_zscore") == 1:
                triggers.append("VOLUME_SPIKE_ZSCORE")

            vol_ann = r.get("volatility_annualized")
            ret_1d = r.get("ret_1d")
            if vol_ann is not None and vol_ann > 0 and ret_1d is not None:
                daily_sigma = vol_ann / math.sqrt(252.0)
                if abs(ret_1d) >= 2.5 * daily_sigma:
                    triggers.append("RETURN_VOLATILITY_SPIKE")

            if triggers:
                r["triggers"] = triggers
                anomalies.append(r)

        return anomalies

    def decompose_movement(
        self,
        symbol: str,
        trading_date: str,
        ret_1d: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Performs three-tier mathematical decomposition:
        Total Return = Market Component + Sector Component + Idiosyncratic Residual.

        Market Component = Beta_Nifty * R_Nifty
        Sector Component = Beta_Sector * R_Sector
        Residual = Total Return - (Market Component + Sector Component)
        """
        # 1. Fetch stock return and beta
        if ret_1d is None:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT ret_1d, beta_60d_nifty FROM quant_factors_daily WHERE symbol = ? AND trading_date = ?",
                    (symbol, trading_date)
                )
                factor_row = cur.fetchone()
                if factor_row and factor_row["ret_1d"] is not None:
                    ret_1d = float(factor_row["ret_1d"])
                    beta_nifty = float(factor_row["beta_60d_nifty"]) if factor_row["beta_60d_nifty"] is not None else 1.0
                else:
                    # Fallback to ohlcv_daily calculation
                    cur = conn.execute(
                        """
                        SELECT close FROM ohlcv_daily 
                        WHERE symbol = ? AND trading_date <= ? 
                        ORDER BY trading_date DESC LIMIT 2
                        """,
                        (symbol, trading_date)
                    )
                    closes = cur.fetchall()
                    if len(closes) >= 2 and float(closes[1][0]) > 0:
                        ret_1d = (float(closes[0][0]) - float(closes[1][0])) / float(closes[1][0])
                    else:
                        ret_1d = 0.0
                    beta_nifty = 1.0
        else:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT beta_60d_nifty FROM quant_factors_daily WHERE symbol = ? AND trading_date = ?",
                    (symbol, trading_date)
                )
                row = cur.fetchone()
                beta_nifty = float(row["beta_60d_nifty"]) if row and row["beta_60d_nifty"] is not None else 1.0

        # 2. Fetch Nifty 50 Return on trading_date
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT close FROM index_daily 
                WHERE index_name = 'NIFTY 50' AND index_type = 'PRI' AND trading_date <= ? 
                ORDER BY trading_date DESC LIMIT 2
                """,
                (trading_date,)
            )
            nifty_rows = cur.fetchall()
            if len(nifty_rows) >= 2 and float(nifty_rows[1][0]) > 0:
                market_return = (float(nifty_rows[0][0]) - float(nifty_rows[1][0])) / float(nifty_rows[1][0])
            else:
                market_return = 0.0

        market_component = round(beta_nifty * market_return, 6)

        # 3. Fetch Sector Return on trading_date
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT sector, industry FROM securities_master WHERE symbol = ?",
                (symbol,)
            )
            sec_row = cur.fetchone()
            if not sec_row:
                cur = conn.execute("SELECT sector FROM user_watchlists WHERE symbol = ?", (symbol,))
                wl_row = cur.fetchone()
                sector_name = wl_row["sector"] if wl_row else "Unclassified"
                industry_name = "General"
            else:
                sector_name = sec_row["sector"] or "Unclassified"
                industry_name = sec_row["industry"] or "General"

        b_type, b_name, cand_peers, is_proxy, _ = resolve_sector_benchmark(
            symbol=symbol,
            sector=sector_name,
            industry=industry_name
        )

        sector_return = 0.0
        beta_sector = 1.0

        if b_type == SectorBenchmarkType.OFFICIAL_SECTOR_PRI:
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    """
                    SELECT close FROM index_daily 
                    WHERE index_name = ? AND index_type = 'PRI' AND trading_date <= ? 
                    ORDER BY trading_date DESC LIMIT 2
                    """,
                    (b_name, trading_date)
                )
                s_rows = cur.fetchall()
                if len(s_rows) >= 2 and float(s_rows[1][0]) > 0:
                    sector_return = (float(s_rows[0][0]) - float(s_rows[1][0])) / float(s_rows[1][0])
                else:
                    sector_return = market_return
        elif b_type == SectorBenchmarkType.SYNTHETIC_PEER_BASKET and cand_peers:
            peer_rets = []
            with self.db.get_connection() as conn:
                for p in cand_peers:
                    cur = conn.execute(
                        """
                        SELECT close FROM ohlcv_daily 
                        WHERE symbol = ? AND trading_date <= ? 
                        ORDER BY trading_date DESC LIMIT 2
                        """,
                        (p, trading_date)
                    )
                    p_rows = cur.fetchall()
                    if len(p_rows) >= 2 and float(p_rows[1][0]) > 0:
                        peer_rets.append((float(p_rows[0][0]) - float(p_rows[1][0])) / float(p_rows[1][0]))
            if peer_rets:
                sector_return = sum(peer_rets) / float(len(peer_rets))
            else:
                sector_return = market_return
        else:
            sector_return = market_return

        # Sector Component: Beta_Sector * (Sector_Return - Market_Return) or Beta_Sector * Sector_Return
        # In multi-factor decomposition, Sector Component captures sector effect: Beta_Sector * Sector_Return
        sector_component = round(beta_sector * sector_return, 6)

        # 4. Expected Return & Idiosyncratic Residual
        # Expected Return = Market Component + Sector Component
        expected_return = round(market_component + sector_component, 6)
        residual = round(ret_1d - expected_return, 6)

        # Exact identity check adjustment if rounding caused micro-drift
        conservation_error = round(ret_1d - (market_component + sector_component + residual), 10)
        if abs(conservation_error) > 0:
            residual = round(residual + conservation_error, 6)

        return {
            "total_return": round(ret_1d, 6),
            "market_component": market_component,
            "sector_component": sector_component,
            "residual": residual,
            "expected_return": expected_return,
            "beta_nifty": round(beta_nifty, 4),
            "market_return": round(market_return, 6),
            "beta_sector": round(beta_sector, 4),
            "sector_return": round(sector_return, 6),
            "sector_name": sector_name
        }

    def correlate_disclosures(
        self,
        symbol: str,
        trading_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Searches corporate_disclosures for official filings within t in [-1, +1] of trading_date.
        If a verified disclosure exists, computes CAR[-1, +1] using OLS market model.
        """
        calendar = self.get_trading_calendar()
        if trading_date not in calendar:
            # Look up trading dates from stock history
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT trading_date FROM ohlcv_daily WHERE symbol = ? ORDER BY trading_date ASC",
                    (symbol,)
                )
                dates = [r[0] for r in cur.fetchall()]
        else:
            dates = calendar

        if trading_date not in dates:
            return None

        idx = dates.index(trading_date)
        prev_date = dates[idx - 1] if idx > 0 else trading_date
        next_date = dates[idx + 1] if idx + 1 < len(dates) else trading_date
        window_dates = [prev_date, trading_date, next_date]

        # Query disclosures
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM corporate_disclosures 
                WHERE symbol = ? 
                  AND (
                      effective_session_date IN (?, ?, ?)
                      OR substr(broadcast_timestamp, 1, 10) IN (?, ?, ?)
                  )
                ORDER BY CASE WHEN verification_status = 'VERIFIED' THEN 0 ELSE 1 END, broadcast_timestamp DESC
                """,
                (symbol, *window_dates, *window_dates)
            )
            disclosures = [dict(r) for r in cur.fetchall()]

        if not disclosures:
            return None

        best_disc = disclosures[0]
        eff_date = best_disc.get("effective_session_date") or trading_date

        # Compute Event Study CAR[-1, +1] if effective date is available
        car_val: Optional[float] = None
        event_study_details: Optional[Dict[str, Any]] = None

        try:
            study = self.event_study_engine.run_event_study(
                symbol=symbol,
                effective_event_date=eff_date,
                verification_status=best_disc.get("verification_status", "PENDING_VERIFICATION")
            )
            if study.get("status") == "COMPLETED":
                car_val = study.get("car_minus1_plus1")
            event_study_details = study
        except Exception:
            event_study_details = None

        return {
            "disclosure_id": best_disc["disclosure_id"],
            "symbol": symbol,
            "category": best_disc.get("category", "GENERAL"),
            "broadcast_timestamp": best_disc.get("broadcast_timestamp"),
            "effective_session_date": eff_date,
            "subject": best_disc.get("subject", "Corporate Announcement"),
            "details_summary": best_disc.get("details_summary"),
            "source_url": best_disc.get("source_url"),
            "verification_status": best_disc.get("verification_status", "PENDING_VERIFICATION"),
            "audit_status": best_disc.get("audit_status"),
            "car_minus1_plus1": car_val,
            "event_study_details": event_study_details
        }

    def analyze_attribution(
        self,
        symbol: str,
        trading_date: str,
        triggers: Optional[List[str]] = None
    ) -> AttributionResult:
        """
        Executes complete movement attribution for a single session:
        - 3-tier decomposition (Market, Sector, Residual)
        - Proximity disclosure correlation & CAR[-1, +1]
        - Taxonomy classification
        """
        decomp = self.decompose_movement(symbol, trading_date)
        disc_match = self.correlate_disclosures(symbol, trading_date)

        total_r = decomp["total_return"]
        mkt_comp = decomp["market_component"]
        sec_comp = decomp["sector_component"]
        resid = decomp["residual"]

        has_disc = disc_match is not None
        car_val = disc_match.get("car_minus1_plus1") if disc_match else None

        # Determine Attribution Taxonomy Tag
        if has_disc:
            attribution_tag = "DISCLOSURE_CORRELATED_EVENT"
            cat = disc_match.get("category", "FILING")
            car_str = f" (CAR[-1, +1]: {car_val:+.2%})" if car_val is not None else ""
            summary = (
                f"Movement correlated with official corporate disclosure '{disc_match['disclosure_id']}' "
                f"({cat}){car_str}. Idiosyncratic residual of {resid:+.2%} reflects specific information re-pricing."
            )
        else:
            if abs(resid) < 0.005 and abs(mkt_comp) >= 0.005:
                attribution_tag = "MARKET_BETA_DRIVEN"
                summary = (
                    f"Session movement predominantly explained by broad market systematic exposure "
                    f"(Market component: {mkt_comp:+.2%}, Beta: {decomp['beta_nifty']:.2f})."
                )
            elif abs(resid) < 0.005 and abs(sec_comp) >= 0.005:
                attribution_tag = "SECTOR_SYSTEMATIC_FLOW"
                summary = (
                    f"Session movement predominantly driven by sector-wide systematic flow "
                    f"in {decomp['sector_name']} (Sector component: {sec_comp:+.2%})."
                )
            else:
                attribution_tag = "UNEXPLAINED_IDIOSYNCRATIC_FLOW"
                summary = (
                    f"Anomalous return residual of {resid:+.2%} has no temporally correlated official "
                    f"corporate disclosures in [-1, +1] trading window. Classified as unexplained idiosyncratic flow."
                )

        return AttributionResult(
            symbol=symbol,
            trading_date=trading_date,
            total_return=total_r,
            market_component=mkt_comp,
            sector_component=sec_comp,
            residual=resid,
            expected_return=decomp["expected_return"],
            beta_nifty=decomp["beta_nifty"],
            market_return=decomp["market_return"],
            beta_sector=decomp["beta_sector"],
            sector_return=decomp["sector_return"],
            sector_name=decomp["sector_name"],
            anomaly_triggers=triggers or ["MANUAL_ANALYSIS"],
            has_correlated_disclosure=has_disc,
            correlated_disclosure=disc_match,
            car_minus1_plus1=car_val,
            attribution_tag=attribution_tag,
            explanation_summary=summary
        )

    def scan_and_attribute_universe(
        self,
        lookback_sessions: int = 30
    ) -> List[AttributionResult]:
        """
        Scans all universe instruments across the trailing lookback_sessions trading days,
        detects volume/volatility anomalies, and computes attribution results.
        """
        anomalies = self.scan_anomalies(lookback_sessions=lookback_sessions)
        results = []
        for anom in anomalies:
            sym = anom["symbol"]
            t_date = anom["trading_date"]
            trigs = anom.get("triggers", [])
            attr = self.analyze_attribution(symbol=sym, trading_date=t_date, triggers=trigs)
            results.append(attr)

        return results
