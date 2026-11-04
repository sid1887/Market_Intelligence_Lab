import math
import re
import datetime
from typing import Dict, Any, List, Optional, Tuple

class FundamentalsEngine:
    """
    Quantitative engine for point-in-time financial statement analysis,
    trailing twelve month (TTM) metric normalization, corporate action adjustments,
    sector-aware valuation multiples, and cross-sectional factor ranking.
    """

    FINANCIAL_SECTORS = {
        "FINANCIAL SERVICES",
        "BANKING",
        "BANKS",
        "FINANCIALS",
        "NBFC",
        "INSURANCE"
    }

    def __init__(self, db_manager=None):
        self.db = db_manager

    @staticmethod
    def parse_iso_date(date_str: str) -> datetime.date:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

    def get_as_of_statements(
        self,
        symbol: str,
        as_of_date: str,
        db=None,
        reporting_basis: str = "CONSOLIDATED",
        period_nature: str = "DISCRETE_QUARTER",
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Retrieves point-in-time financial statements published strictly on or before `as_of_date`.
        Enforces:
        - effective_session_date <= as_of_date (or publication_date <= as_of_date if effective_session_date is null)
        - is_pit_eligible = 1
        - Deduplication selects latest statement_version per period_end_date.
        """
        active_db = db or self.db
        if not active_db:
            raise ValueError("DatabaseManager instance required to query statements")

        return active_db.get_point_in_time_statements(
            symbol=symbol,
            as_of_date=as_of_date,
            reporting_basis=reporting_basis,
            period_nature=period_nature,
            limit=limit
        )

    def compute_ttm_metrics(
        self,
        discrete_quarters: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Normalizes flow and balance-sheet items across available discrete quarters.
        Enforces:
        - Prevents cumulative YTD items from being summed as discrete quarters.
        - Sums flow items across the 4 most recent discrete quarters.
        - Selects balance sheet snapshot items from the most recent available quarter.
        - Computes YoY growth by comparing quarter 0 with quarter 4 (same quarter last year).
        """
        if not discrete_quarters:
            return {
                "statements_count_ttm": 0,
                "data_quality_flag": "NO_STATEMENTS",
                "ttm_revenue": None,
                "ttm_ebitda": None,
                "ttm_ebit": None,
                "ttm_net_profit": None,
                "latest_equity": None,
                "latest_debt": None,
                "latest_cash": None,
                "shares_outstanding": None,
                "latest_statement_id": None,
                "latest_statement_date": None,
                "revenue_growth_yoy": None,
                "net_profit_growth_yoy": None,
                "eps_growth_yoy": None
            }

        # Validate that all passed statements are DISCRETE_QUARTER
        for q in discrete_quarters:
            if q.get("period_nature") != "DISCRETE_QUARTER":
                raise ValueError(
                    f"compute_ttm_metrics requires DISCRETE_QUARTER statements, found: {q.get('period_nature')}"
                )

        # Sort descending by period_end_date
        sorted_quarters = sorted(
            discrete_quarters,
            key=lambda x: x.get("period_end_date", ""),
            reverse=True
        )

        q_count = len(sorted_quarters)
        quarters_to_sum = sorted_quarters[:min(4, q_count)]
        count_used = len(quarters_to_sum)

        # Flow items across available quarters
        total_rev = 0.0
        has_rev = False
        for q in quarters_to_sum:
            rev = q.get("total_revenue")
            if rev is None:
                rev = q.get("revenue_operations")
            if rev is not None:
                total_rev += float(rev)
                has_rev = True

        total_ebitda = 0.0
        has_ebitda = False
        for q in quarters_to_sum:
            eb = q.get("ebitda")
            if eb is not None:
                total_ebitda += float(eb)
                has_ebitda = True

        total_ebit = 0.0
        has_ebit = False
        for q in quarters_to_sum:
            eb = q.get("ebit")
            if eb is not None:
                total_ebit += float(eb)
                has_ebit = True

        total_pat = 0.0
        has_pat = False
        for q in quarters_to_sum:
            pat = q.get("net_profit")
            if pat is not None:
                total_pat += float(pat)
                has_pat = True

        # Strict TTM Discipline:
        # A true Trailing Twelve Months (TTM) metric strictly requires 4 discrete quarters.
        # If fewer than 4 quarters are available, flow items must NOT be treated as a full year's TTM.
        if count_used == 4:
            # Check for corporate demerger boundary & reporting perimeter consistency
            has_pre_demerger = any(
                q.get("restatement_reason") == "PRE_DEMERGER_COMBINED_TATA_MOTORS"
                for q in quarters_to_sum
            )
            has_post_demerger = any(
                q.get("restatement_reason") == "POST_DEMERGER_TMPV"
                for q in quarters_to_sum
            )
            if has_pre_demerger and has_post_demerger:
                quality_flag = "INCONSISTENT_REPORTING_PERIMETER"
                ttm_rev = None
                ttm_ebitda = None
                ttm_ebit = None
                ttm_pat = None
            else:
                quality_flag = None
                ttm_rev = round(total_rev, 2) if has_rev else None
                ttm_ebitda = round(total_ebitda, 2) if has_ebitda else None
                ttm_ebit = round(total_ebit, 2) if has_ebit else None
                ttm_pat = round(total_pat, 2) if has_pat else None
        else:
            quality_flag = "INSUFFICIENT_PERIODS_FOR_TTM"
            ttm_rev = None
            ttm_ebitda = None
            ttm_ebit = None
            ttm_pat = None

        # Latest balance sheet snapshot (from newest quarter)
        latest_q = sorted_quarters[0]
        latest_equity = latest_q.get("total_equity")
        latest_debt = latest_q.get("total_debt")
        latest_cash = latest_q.get("cash_and_equivalents")
        shs_out = latest_q.get("shares_outstanding")

        # YoY Quarterly Growth Metrics (comparing latest quarter with same quarter previous year)
        rev_growth_yoy = None
        pat_growth_yoy = None
        eps_growth_yoy = None

        if len(sorted_quarters) >= 5:
            q_curr = sorted_quarters[0]
            q_prev = sorted_quarters[4]  # 4 quarters prior = same quarter last year

            r_curr = q_curr.get("total_revenue") or q_curr.get("revenue_operations")
            r_prev = q_prev.get("total_revenue") or q_prev.get("revenue_operations")
            if r_curr is not None and r_prev is not None and float(r_prev) > 0:
                rev_growth_yoy = ((float(r_curr) - float(r_prev)) / float(r_prev)) * 100.0

            p_curr = q_curr.get("net_profit")
            p_prev = q_prev.get("net_profit")
            if p_curr is not None and p_prev is not None and abs(float(p_prev)) > 0:
                pat_growth_yoy = ((float(p_curr) - float(p_prev)) / abs(float(p_prev))) * 100.0

            eps_curr = q_curr.get("diluted_eps") or q_curr.get("basic_eps")
            eps_prev = q_prev.get("diluted_eps") or q_prev.get("basic_eps")
            if eps_curr is not None and eps_prev is not None and abs(float(eps_prev)) > 0:
                eps_growth_yoy = ((float(eps_curr) - float(eps_prev)) / abs(float(eps_prev))) * 100.0

        return {
            "statements_count_ttm": count_used,
            "data_quality_flag": quality_flag,
            "ttm_revenue": ttm_rev,
            "ttm_ebitda": ttm_ebitda,
            "ttm_ebit": ttm_ebit,
            "ttm_net_profit": ttm_pat,
            "partial_period_revenue": round(total_rev, 2) if has_rev else None,
            "partial_period_net_profit": round(total_pat, 2) if has_pat else None,
            "latest_equity": float(latest_equity) if latest_equity is not None else None,
            "latest_debt": float(latest_debt) if latest_debt is not None else None,
            "latest_cash": float(latest_cash) if latest_cash is not None else None,
            "shares_outstanding": float(shs_out) if shs_out is not None else None,
            "latest_statement_id": latest_q.get("statement_id"),
            "latest_statement_date": latest_q.get("period_end_date"),
            "revenue_growth_yoy": round(rev_growth_yoy, 2) if rev_growth_yoy is not None else None,
            "net_profit_growth_yoy": round(pat_growth_yoy, 2) if pat_growth_yoy is not None else None,
            "eps_growth_yoy": round(eps_growth_yoy, 2) if eps_growth_yoy is not None else None
        }

    def adjust_for_corporate_actions(
        self,
        symbol: str,
        statement_date: Optional[str],
        trading_date: str,
        statement_shares: Optional[float],
        db=None
    ) -> Tuple[Optional[float], float]:
        """
        Adjusts shares outstanding and calculates trailing cash dividends.
        - Shares outstanding: If a stock split or bonus issue occurred between statement_date and trading_date,
          adjusts the statement share count to trading_date basis using historical multiplier M_hist <= 1.0.
          N_trading = N_statement / prod(M_hist)
        - Cash dividends: Retrieves all cash dividends in the 365-day trailing window up to trading_date,
          scaling each historical dividend per share by subsequent stock splits/bonuses to date t basis.
        """
        active_db = db or self.db
        if not active_db:
            return statement_shares, 0.0

        # Query corporate actions for symbol
        with active_db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT action_type, ex_date, purpose, adjustment_factor
                FROM corporate_actions
                WHERE symbol = ?
                ORDER BY ex_date ASC;
                """,
                (symbol,)
            )
            actions = [dict(row) for row in cursor.fetchall()]

        # 1. Share count adjustment between statement_date and trading_date
        adjusted_shares = statement_shares
        if statement_shares is not None and statement_date is not None:
            cum_mult = 1.0
            for act in actions:
                atype = act.get("action_type")
                ex_d = act.get("ex_date")
                factor = act.get("adjustment_factor")
                if atype in ("SPLIT", "BONUS") and factor is not None and float(factor) > 0:
                    if statement_date < ex_d <= trading_date:
                        cum_mult *= float(factor)
            if cum_mult > 0:
                adjusted_shares = statement_shares / cum_mult

        # 2. Trailing cash dividends (1 year lookback up to trading_date)
        t_date = self.parse_iso_date(trading_date)
        lookback_date = (t_date - datetime.timedelta(days=365)).isoformat()

        trailing_div_sum = 0.0
        for act in actions:
            atype = (act.get("action_type") or "").upper()
            ex_d = act.get("ex_date")
            purpose = act.get("purpose") or ""
            div_val = 0.0
            if "DIVIDEND" in atype or "DIVIDEND" in purpose.upper():
                match = re.search(r"Rs\.?\s*(\d+(?:\.\d+)?)", purpose, re.IGNORECASE)
                if match:
                    div_val = float(match.group(1))

            if div_val > 0 and lookback_date <= ex_d <= trading_date:
                div_amount = div_val
                # Scale dividend if any split/bonus occurred between ex_d and trading_date
                split_bonus_mult = 1.0
                for other in actions:
                    if other.get("action_type") in ("SPLIT", "BONUS"):
                        o_ex = other.get("ex_date")
                        o_fac = other.get("adjustment_factor")
                        if o_fac is not None and float(o_fac) > 0 and ex_d < o_ex <= trading_date:
                            split_bonus_mult *= float(o_fac)
                trailing_div_sum += div_amount * split_bonus_mult

        return adjusted_shares, round(trailing_div_sum, 4)

    def calculate_fundamental_factors(
        self,
        symbol: str,
        trading_date: str,
        db=None,
        reporting_basis: str = "CONSOLIDATED"
    ) -> Dict[str, Any]:
        """
        Computes point-in-time daily fundamental factors and valuation multiples for a company on trading_date.
        Enforces:
        - Point-in-time financial statement retrieval (zero look-ahead bias).
        - Market Cap / TTM Net Profit valuation formulation (eliminating share count discrepancies).
        - Sector-aware ratio applicability: Sets EV/EBITDA, D/E, and ROCE to NULL for Banks and Financials.
        - Quality flags for negative earnings (P/E = NULL) and negative equity (P/B = NULL).
        """
        active_db = db or self.db
        if not active_db:
            raise ValueError("DatabaseManager required")

        # 1. Fetch close price on trading_date
        with active_db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT close FROM ohlcv_daily
                WHERE symbol = ? AND trading_date <= ?
                ORDER BY trading_date DESC LIMIT 1;
                """,
                (symbol, trading_date)
            )
            row = cursor.fetchone()
            if not row or row["close"] is None:
                raise ValueError(f"No OHLCV price available for {symbol} on or before {trading_date}")
            close_price = float(row["close"])

            # 2. Fetch sector from securities_master
            s_cur = conn.execute(
                "SELECT sector, industry FROM securities_master WHERE symbol = ?;",
                (symbol,)
            )
            s_row = s_cur.fetchone()
            sector = (s_row["sector"] or "Unknown") if s_row else "Unknown"

        # 3. Retrieve point-in-time statements (prefer requested reporting_basis, fallback to STANDALONE if empty)
        statements = self.get_as_of_statements(
            symbol=symbol,
            as_of_date=trading_date,
            db=active_db,
            reporting_basis=reporting_basis,
            period_nature="DISCRETE_QUARTER",
            limit=8
        )
        if not statements and reporting_basis == "CONSOLIDATED":
            statements = self.get_as_of_statements(
                symbol=symbol,
                as_of_date=trading_date,
                db=active_db,
                reporting_basis="STANDALONE",
                period_nature="DISCRETE_QUARTER",
                limit=8
            )

        # 4. Compute TTM metrics
        ttm = self.compute_ttm_metrics(statements)

        # 5. Corporate actions adjustment for shares and trailing dividends
        stmt_date = ttm.get("latest_statement_date")
        raw_shares = ttm.get("shares_outstanding")
        adj_shares, trailing_divs = self.adjust_for_corporate_actions(
            symbol=symbol,
            statement_date=stmt_date,
            trading_date=trading_date,
            statement_shares=raw_shares,
            db=active_db
        )

        # 6. Market Capitalization (INR Crore)
        # Note: Price is in INR per share. Shares outstanding in statement is absolute number of shares.
        # Market Cap (INR Crore) = (close_price * adj_shares) / 10,000,000 (1 Crore = 10^7)
        market_cap_cr = None
        ttm_eps_adj = None
        if adj_shares is not None and adj_shares > 0:
            market_cap_cr = round((close_price * adj_shares) / 1e7, 2)
            if ttm.get("ttm_net_profit") is not None:
                # TTM Net Profit is in INR Crore -> convert to INR: profit * 1e7 / shares
                ttm_eps_adj = round((ttm["ttm_net_profit"] * 1e7) / adj_shares, 2)

        # 7. Sector-aware applicability & ratio computation
        is_financial = sector.upper() in self.FINANCIAL_SECTORS
        metric_flag = "FINANCIAL_SECTOR_ADJUSTED" if is_financial else "STANDARD_INDUSTRIAL"
        data_quality_flags = []
        if ttm.get("data_quality_flag"):
            data_quality_flags.append(ttm["data_quality_flag"])

        # P/E Ratio
        pe_ratio = None
        pat = ttm.get("ttm_net_profit")
        if pat is not None:
            if pat <= 0:
                data_quality_flags.append("NEGATIVE_EARNINGS")
                pe_ratio = None
            elif market_cap_cr is not None and market_cap_cr > 0:
                pe_ratio = round(market_cap_cr / pat, 2)
            elif ttm_eps_adj is not None and ttm_eps_adj > 0:
                pe_ratio = round(close_price / ttm_eps_adj, 2)

        # P/B Ratio
        pb_ratio = None
        equity = ttm.get("latest_equity")
        if equity is not None:
            if equity <= 0:
                data_quality_flags.append("NEGATIVE_EQUITY")
                pb_ratio = None
            elif market_cap_cr is not None and market_cap_cr > 0:
                pb_ratio = round(market_cap_cr / equity, 2)

        # P/S Ratio
        ps_ratio = None
        rev = ttm.get("ttm_revenue")
        if rev is not None and rev > 0 and market_cap_cr is not None and market_cap_cr > 0:
            ps_ratio = round(market_cap_cr / rev, 2)

        # EV / EBITDA & D/E & ROCE (Excluded for Financials)
        ev_ebitda = None
        debt_to_equity = None
        roce_pct = None

        if not is_financial:
            # EV = Market Cap + Debt - Cash
            debt = ttm.get("latest_debt") or 0.0
            cash = ttm.get("latest_cash") or 0.0
            ebitda = ttm.get("ttm_ebitda")

            if market_cap_cr is not None and ebitda is not None and ebitda > 0:
                ev = market_cap_cr + debt - cash
                ev_ebitda = round(ev / ebitda, 2)

            # Debt-to-Equity
            if equity is not None and equity > 0:
                debt_to_equity = round(debt / equity, 2)

            # ROCE % = EBIT / (Equity + Debt) * 100
            ebit = ttm.get("ttm_ebit")
            if ebit is not None and equity is not None and (equity + debt) > 0:
                roce_pct = round((ebit / (equity + debt)) * 100.0, 2)

        # Dividend Yield %
        div_yield_ttm = None
        if close_price > 0:
            div_yield_ttm = round((trailing_divs / close_price) * 100.0, 2)

        # Margins & ROE
        op_margin = None
        if rev is not None and rev > 0 and ttm.get("ttm_ebit") is not None:
            op_margin = round((ttm["ttm_ebit"] / rev) * 100.0, 2)

        net_margin = None
        if rev is not None and rev > 0 and pat is not None:
            net_margin = round((pat / rev) * 100.0, 2)

        roe_pct = None
        if equity is not None and equity > 0 and pat is not None:
            roe_pct = round((pat / equity) * 100.0, 2)

        quality_flag_str = ";".join(data_quality_flags) if data_quality_flags else "COMPLETE"

        return {
            "symbol": symbol,
            "trading_date": trading_date,
            "close_price": close_price,
            "shares_outstanding": adj_shares,
            "market_cap_inr_crore": market_cap_cr,
            "ttm_revenue": rev,
            "ttm_ebitda": ttm.get("ttm_ebitda"),
            "ttm_ebit": ttm.get("ttm_ebit"),
            "ttm_net_profit": pat,
            "ttm_eps_adjusted": ttm_eps_adj,
            "latest_equity": equity,
            "latest_debt": ttm.get("latest_debt"),
            "latest_cash": ttm.get("latest_cash"),
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "ps_ratio": ps_ratio,
            "ev_ebitda": ev_ebitda,
            "dividend_yield_ttm": div_yield_ttm,
            "roe_pct": roe_pct,
            "roce_pct": roce_pct,
            "debt_to_equity": debt_to_equity,
            "operating_margin_ttm": op_margin,
            "net_margin_ttm": net_margin,
            "revenue_growth_yoy": ttm.get("revenue_growth_yoy"),
            "net_profit_growth_yoy": ttm.get("net_profit_growth_yoy"),
            "eps_growth_yoy": ttm.get("eps_growth_yoy"),
            "sector": sector,
            "sector_pe_median": None,
            "pe_vs_sector_spread": None,
            "pe_percentile_sector": None,
            "valuation_decile_universe": None,
            "statements_count_ttm": ttm.get("statements_count_ttm", 0),
            "data_quality_flag": quality_flag_str,
            "metric_applicability_flag": metric_flag,
            "latest_statement_id": ttm.get("latest_statement_id"),
            "calculated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    @staticmethod
    def compute_sector_relative_factors(
        factors_on_date: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculates cross-sectional sector-relative metrics and universe valuation deciles
        across a batch of daily fundamental factor records on a single trading date.
        - Sector Median P/E computed across profitable companies (pe_ratio > 0).
        - Relative Spread: PE_i - Sector_Median_PE.
        - Percentile Rank within Sector (0 to 100).
        - Valuation Decile across Universe (1 = lowest PE / cheapest decile, 10 = highest PE).
        """
        if not factors_on_date:
            return []

        # 1. Group by sector
        by_sector: Dict[str, List[Dict[str, Any]]] = {}
        for f in factors_on_date:
            sec = f.get("sector") or "Unknown"
            by_sector.setdefault(sec, []).append(f)

        # 2. Compute sector medians & percentiles
        for sec, items in by_sector.items():
            valid_pes = [
                float(it["pe_ratio"]) for it in items
                if it.get("pe_ratio") is not None and float(it["pe_ratio"]) > 0
            ]
            if valid_pes:
                valid_pes.sort()
                n = len(valid_pes)
                if n % 2 == 1:
                    median_pe = valid_pes[n // 2]
                else:
                    median_pe = (valid_pes[n // 2 - 1] + valid_pes[n // 2]) / 2.0
                median_pe = round(median_pe, 2)
            else:
                median_pe = None

            for it in items:
                it["sector_pe_median"] = median_pe
                pe = it.get("pe_ratio")
                if pe is not None and median_pe is not None:
                    it["pe_vs_sector_spread"] = round(float(pe) - median_pe, 2)
                    # Percentile rank within sector
                    if len(valid_pes) > 1:
                        rank = sum(1 for p in valid_pes if p <= float(pe))
                        it["pe_percentile_sector"] = round(((rank - 1) / (len(valid_pes) - 1)) * 100.0, 2)
                    else:
                        it["pe_percentile_sector"] = 50.0
                else:
                    it["pe_vs_sector_spread"] = None
                    it["pe_percentile_sector"] = None

        # 3. Valuation Decile across Universe
        universe_valid = [
            it for it in factors_on_date
            if it.get("pe_ratio") is not None and float(it["pe_ratio"]) > 0
        ]
        universe_valid.sort(key=lambda x: float(x["pe_ratio"]))
        m = len(universe_valid)
        if m > 0:
            for idx, it in enumerate(universe_valid):
                # Decile 1 to 10
                decile = min(10, int((idx / m) * 10) + 1)
                it["valuation_decile_universe"] = decile

        for it in factors_on_date:
            if it.get("pe_ratio") is None or float(it.get("pe_ratio") or 0) <= 0:
                it["valuation_decile_universe"] = None

        return factors_on_date


# ====================================================================
# Milestone B3.3: Deterministic Fundamental Ratio Calculators
# ====================================================================

def calculate_ttm_pe_ratio(current_price: Optional[float], ttm_eps: Optional[float]) -> Optional[float]:
    """
    Trailing Twelve Months (TTM) P/E Ratio = Current Price / TTM EPS.
    Returns None if ttm_eps <= 0 or current_price <= 0 (safeguard against negative earnings/prices).
    """
    if current_price is None or ttm_eps is None:
        return None
    try:
        cp = float(current_price)
        eps = float(ttm_eps)
        if cp <= 0 or eps <= 0:
            return None
        return round(cp / eps, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_roe(
    net_profit_annualized: Optional[float],
    total_equity: Optional[float],
    as_percentage: bool = True
) -> Optional[float]:
    """
    Return on Equity (ROE) = Net Profit (Annualized) / Total Equity.
    Returns None if total_equity <= 0 (safeguard against negative or zero net worth).
    """
    if net_profit_annualized is None or total_equity is None:
        return None
    try:
        np = float(net_profit_annualized)
        eq = float(total_equity)
        if eq <= 0:
            return None
        ratio = np / eq
        return round(ratio * 100.0, 2) if as_percentage else round(ratio, 4)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_debt_to_equity(
    total_debt: Optional[float],
    total_equity: Optional[float]
) -> Optional[float]:
    """
    Debt-to-Equity Ratio = Total Debt / Total Equity.
    Returns None if total_equity <= 0.
    Returns 0.0 if total_debt <= 0.
    """
    if total_equity is None:
        return None
    try:
        eq = float(total_equity)
        if eq <= 0:
            return None
        debt = float(total_debt) if total_debt is not None else 0.0
        if debt <= 0:
            return 0.0
        return round(debt / eq, 4)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def calculate_opm(
    ebitda: Optional[float],
    revenue: Optional[float],
    as_percentage: bool = True
) -> Optional[float]:
    """
    Operating Profit Margin (OPM %) = (EBITDA / Revenue) * 100.
    Returns None if revenue <= 0 or ebitda is None.
    """
    if ebitda is None or revenue is None:
        return None
    try:
        eb = float(ebitda)
        rev = float(revenue)
        if rev <= 0:
            return None
        ratio = eb / rev
        return round(ratio * 100.0, 2) if as_percentage else round(ratio, 4)
    except (ValueError, TypeError, ZeroDivisionError):
        return None

