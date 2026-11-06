"""
Market Intelligence Lab — Compounding Feedback Evaluator (Milestone B9.0).

Autonomous self-evaluating feedback loop that continuously measures forecast realization,
tracks confidence cone containment (80% and 95%), evaluates post-catalyst return drift,
and dynamically tunes weights for institutional conviction scoring.
"""

import math
import uuid
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager
from src.api.utils import sanitize_for_json

logger = logging.getLogger(__name__)


class FeedbackEvaluator:
    """
    Evaluates historical predictions against realized market prices, logs outcomes to audit ledgers,
    and dynamically tunes multi-factor weights based on empirical model reliability.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def record_forecast(
        self,
        symbol: str,
        prediction_date: str,
        horizon_days: int,
        target_evaluation_date: str,
        current_price: float,
        expected_price: float,
        lower_80: float,
        upper_80: float,
        lower_95: float,
        upper_95: float
    ) -> str:
        """Records a new econometric forecast to the audit ledger."""
        rec = {
            "symbol": symbol.upper(),
            "prediction_date": prediction_date,
            "horizon_days": horizon_days,
            "target_evaluation_date": target_evaluation_date,
            "current_price": float(current_price),
            "expected_price": float(expected_price),
            "lower_80": float(lower_80),
            "upper_80": float(upper_80),
            "lower_95": float(lower_95),
            "upper_95": float(upper_95)
        }
        return self.db.record_forecast_prediction(rec)

    def record_catalyst(
        self,
        symbol: str,
        article_id: str,
        published_at: str,
        direction: str,
        price_at_publish: float
    ) -> str:
        """Records a news sentiment impact classification to the catalyst audit ledger."""
        rec = {
            "symbol": symbol.upper(),
            "article_id": article_id,
            "published_at": published_at,
            "direction": direction.upper(),
            "price_at_publish": float(price_at_publish)
        }
        return self.db.record_catalyst_prediction(rec)

    def evaluate_past_predictions(self, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates pending forecast and catalyst predictions whose target realization dates have arrived.
        """
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        current_date = as_of_date or datetime.date.today().strftime("%Y-%m-%d")

        evaluated_forecasts = 0
        evaluated_catalysts = 0

        # -------------------------------------------------------------
        # 1. Evaluate Pending Forecasts
        # -------------------------------------------------------------
        pending_fc = self.db.get_pending_forecast_audits(current_date)
        # Get global latest settled session in ohlcv_daily (P0-04, ADR-0008)
        with self.db.get_connection() as conn:
            cur_max = conn.execute("SELECT MAX(trading_date) FROM ohlcv_daily WHERE series = 'EQ';")
            max_row = cur_max.fetchone()
            latest_settled_date = max_row[0] if max_row and max_row[0] else ""

            for fc in pending_fc:
                audit_id = fc["id"]
                sym = fc["symbol"]
                target_date = fc["target_evaluation_date"]
                exp_price = float(fc["expected_price"])
                l80 = float(fc["lower_80"])
                u80 = float(fc["upper_80"])
                l95 = float(fc["lower_95"])
                u95 = float(fc["upper_95"])

                # P0-04: Strict maturity guard — never evaluate before market session reaches target_date
                if not latest_settled_date or latest_settled_date < target_date:
                    continue

                # Find realized close on target_date or immediate next valid session (within 4 calendar days)
                cur = conn.execute(
                    """
                    SELECT close, trading_date FROM ohlcv_daily
                    WHERE symbol = ? AND series = 'EQ' AND trading_date >= ?
                    ORDER BY trading_date ASC LIMIT 1;
                    """,
                    (sym, target_date)
                )
                bar = cur.fetchone()

                # Strictly prohibit backward fallback (no trading_date <= target_date lookup!)
                if bar and bar["close"] is not None:
                    bar_date = bar["trading_date"]
                    lag_days = (datetime.date.fromisoformat(bar_date) - datetime.date.fromisoformat(target_date)).days
                    if lag_days <= 4:
                        realized = float(bar["close"])
                        w80 = 1 if (l80 <= realized <= u80) else 0
                        w95 = 1 if (l95 <= realized <= u95) else 0
                        err_pct = round(((realized - exp_price) / exp_price) * 100.0, 4) if exp_price > 0 else 0.0

                        self.db.update_forecast_audit(
                            audit_id=audit_id,
                            realized_price=realized,
                            within_80=w80,
                            within_95=w95,
                            error_pct=err_pct,
                            evaluated_at=now_ts
                        )
                        evaluated_forecasts += 1

        # -------------------------------------------------------------
        # 2. Evaluate Pending Catalysts (5 trading days after publish)
        # -------------------------------------------------------------
        pending_cat = self.db.get_pending_catalyst_audits()
        with self.db.get_connection() as conn:
            for cat in pending_cat:
                audit_id = cat["id"]
                sym = cat["symbol"]
                pub_date = cat["published_at"][:10]
                p_pub = float(cat["price_at_publish"])
                direction = cat["direction"].upper()

                # Find 5th trading session after pub_date
                cur = conn.execute(
                    """
                    SELECT close, trading_date FROM ohlcv_daily
                    WHERE symbol = ? AND series = 'EQ' AND trading_date > ?
                    ORDER BY trading_date ASC LIMIT 5;
                    """,
                    (sym, pub_date)
                )
                rows = cur.fetchall()
                if len(rows) >= 5:
                    bar_5d = rows[-1]
                    p_5d = float(bar_5d["close"])
                    ret_5d = round(((p_5d - p_pub) / p_pub) * 100.0, 4) if p_pub > 0 else 0.0

                    is_acc = 0
                    if direction == "BULLISH" and ret_5d > 0.0:
                        is_acc = 1
                    elif direction == "BEARISH" and ret_5d < 0.0:
                        is_acc = 1
                    elif direction == "NEUTRAL" and abs(ret_5d) <= 2.5:
                        is_acc = 1

                    self.db.update_catalyst_audit(
                        audit_id=audit_id,
                        price_5d=p_5d,
                        return_5d=ret_5d,
                        is_accurate=is_acc,
                        evaluated_at=now_ts
                    )
                    evaluated_catalysts += 1

        accuracy_summary = self.db.get_model_accuracy_metrics()
        return {
            "as_of_date": current_date,
            "evaluated_forecasts_count": evaluated_forecasts,
            "evaluated_catalysts_count": evaluated_catalysts,
            "accuracy_summary": accuracy_summary
        }

    def calculate_institutional_conviction(
        self,
        symbol: str,
        tech_score: float,
        fund_score: float,
        news_score: float,
        forecast_score: float
    ) -> Dict[str, Any]:
        """
        Dynamically calculates Institutional Conviction Score (0-100) using weights
        tuned by empirical realization accuracy.
        """
        metrics = self.db.get_model_accuracy_metrics()
        fc_metrics = metrics.get("forecast_model", {})
        cat_metrics = metrics.get("catalyst_model", {})

        contain_80 = fc_metrics.get("containment_80_pct")
        news_acc = cat_metrics.get("directional_accuracy_pct")

        # Baseline weights
        # Fundamentals: 35%, Technicals: 30%, Forecast Cones: 20%, News Sentiment: 15%
        w_fund = 0.35
        w_tech = 0.30
        w_fc = 0.20
        w_news = 0.15

        # Dynamic weight tuning only when empirical accuracy is observed
        if contain_80 is not None:
            if contain_80 >= 85.0:
                w_fc += 0.05
                w_fund -= 0.02
                w_tech -= 0.03
            elif contain_80 < 75.0:
                # Model drift detected: reduce forecast weight, rely more on balance sheet & structural trend
                w_fc -= 0.08
                w_fund += 0.05
                w_tech += 0.03

        if news_acc is not None:
            if news_acc >= 70.0:
                w_news += 0.03
                w_tech -= 0.03
            elif news_acc < 55.0:
                w_news -= 0.05
                w_fund += 0.05

        # Normalize weights to sum exactly to 1.0
        tot_w = w_fund + w_tech + w_fc + w_news
        w_fund /= tot_w
        w_tech /= tot_w
        w_fc /= tot_w
        w_news /= tot_w

        weighted_score = (
            (fund_score * w_fund) +
            (tech_score * w_tech) +
            (forecast_score * w_fc) +
            (news_score * w_news)
        )
        final_score = int(min(100, max(0, round(weighted_score))))

        return {
            "institutional_conviction_score": final_score,
            "weights": {
                "fundamentals": round(w_fund, 3),
                "technicals": round(w_tech, 3),
                "forecast_cone": round(w_fc, 3),
                "news_catalysts": round(w_news, 3)
            },
            "calibration_status": fc_metrics.get("status", "CALIBRATED")
        }

    def get_accuracy_metrics(self) -> Dict[str, Any]:
        """Returns the aggregate system accuracy metrics for API serialization."""
        raw = self.db.get_model_accuracy_metrics()
        return sanitize_for_json(raw)
