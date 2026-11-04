import datetime
from typing import Dict, Any, List, Tuple, Set, Optional

class RecordValidator:
    """Validates equity market records and enforces financial invariants and nullability constraints."""

    VALID_ACTION_TYPES = {"DIVIDEND", "SPLIT", "BONUS", "RIGHTS", "OTHER"}
    VALID_VERIFICATION_STATUSES = {"PENDING_VERIFICATION", "VERIFIED", "SOURCE_UNVERIFIED", "REJECTED"}
    VALID_PERIOD_TYPES = {"Q1", "Q2", "Q3", "Q4", "ANNUAL", "H1", "H2"}
    VALID_PERIOD_NATURES = {"DISCRETE_QUARTER", "CUMULATIVE_YTD", "ANNUAL"}
    VALID_REPORTING_BASES = {"CONSOLIDATED", "STANDALONE"}
    VALID_AUDIT_STATUSES = {"AUDITED", "UNAUDITED", "LIMITED_REVIEW"}
    VALID_TIMESTAMP_BASES = {"EXACT_EXCHANGE_TIMESTAMP", "ANNOUNCEMENT_DATE_VERIFIED", "UNKNOWN_UNTIMED"}

    def __init__(self):
        self.seen_keys: Set[Tuple[str, str, str]] = set()
        self.seen_ca_keys: Set[Tuple[str, str, str]] = set()
        self.seen_disclosure_keys: Set[str] = set()
        self.seen_statement_keys: Set[Tuple[str, str, str, str, str, int]] = set()

    def reset_dedup(self):
        self.seen_keys.clear()
        self.seen_ca_keys.clear()
        self.seen_disclosure_keys.clear()
        self.seen_statement_keys.clear()

    def validate_record(
        self,
        raw: Dict[str, Any],
        source: str = "nse_mcp",
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        if retrieval_timestamp is None:
            retrieval_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Date extraction & format validation
        date_str = raw.get("date") or raw.get("trading_date") or raw.get("Date")
        if not date_str or not isinstance(date_str, str):
            return False, None, "Missing or non-string date"
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return False, None, f"Invalid date format: {date_str}, expected YYYY-MM-DD"

        # 2. Symbol & Series
        symbol = raw.get("symbol") or raw.get("TckrSymb") or raw.get("SYMBOL")
        if not symbol or not isinstance(symbol, str):
            return False, None, "Missing or invalid symbol"
        symbol = symbol.strip().upper()

        series = raw.get("series") or raw.get("SctySrs") or raw.get("SERIES") or "EQ"
        series = str(series).strip().upper()

        # 3. Deduplication check
        dedup_key = (symbol, date_str, series)
        if dedup_key in self.seen_keys:
            return False, None, f"Duplicate observation for {dedup_key}"
        self.seen_keys.add(dedup_key)

        # 4. Mandatory Numeric Prices
        try:
            open_p = float(raw.get("open") if raw.get("open") is not None else raw.get("OpenPric"))
            high_p = float(raw.get("high") if raw.get("high") is not None else raw.get("HghPric"))
            low_p = float(raw.get("low") if raw.get("low") is not None else raw.get("LwPric"))
            close_p = float(raw.get("close") if raw.get("close") is not None else raw.get("ClsPric"))
            volume = int(raw.get("volume") if raw.get("volume") is not None else raw.get("TtlTradgVol", 0))
        except (ValueError, TypeError) as e:
            return False, None, f"Non-numeric price or volume: {e}"

        # 5. Financial & Logical Invariants
        if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
            return False, None, f"Non-positive price observed: O={open_p}, H={high_p}, L={low_p}, C={close_p}"

        if high_p < low_p:
            return False, None, f"High price ({high_p}) is lower than low price ({low_p})"

        # Relaxed tolerance (0.01) for minor exchange rounding differences
        if open_p > high_p + 0.05 or close_p > high_p + 0.05:
            return False, None, f"Open/Close ({open_p}/{close_p}) exceeds High ({high_p})"

        if open_p < low_p - 0.05 or close_p < low_p - 0.05:
            return False, None, f"Open/Close ({open_p}/{close_p}) is below Low ({low_p})"

        if volume < 0:
            return False, None, f"Negative volume observed: {volume}"

        # 6. Optional / Nullable fields (DO NOT coerce to 0 if unavailable)
        ltp_val = raw.get("ltp") if raw.get("ltp") is not None else raw.get("LastPric")
        ltp = float(ltp_val) if ltp_val is not None else None

        prev_val = raw.get("prevClose") if raw.get("prevClose") is not None else raw.get("PrvsClsgPric")
        prev_close = float(prev_val) if prev_val is not None else None

        turnover_val = raw.get("totalTradedValue") if raw.get("totalTradedValue") is not None else raw.get("TtlTrdVal")
        turnover = float(turnover_val) if turnover_val is not None else None

        # Delivery quantity:
        # If payload omits deliveryQty or provides null/None, store None (SQL NULL).
        # In NSE MCP bhavcopy, deliveryQty is often 0 when not published in the cash stream.
        # If deliveryQty is 0 and volume > 0, we treat it as unavailable (NULL) unless explicitly flagged.
        deliv_val = raw.get("deliveryQty")
        if deliv_val is None:
            delivery_qty = None
        elif isinstance(deliv_val, (int, float)):
            deliv_int = int(deliv_val)
            # In NSE MCP Bhavcopy, deliveryQty: 0 on all active trading days indicates unpopulated/unavailable
            if deliv_int == 0 and volume > 0:
                delivery_qty = None
            else:
                delivery_qty = deliv_int
        else:
            delivery_qty = None

        cleaned: Dict[str, Any] = {
            "symbol": symbol,
            "trading_date": date_str,
            "series": series,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "ltp": ltp,
            "prev_close": prev_close,
            "volume": volume,
            "turnover": turnover,
            "delivery_qty": delivery_qty,
            "source": source,
            "retrieval_timestamp": retrieval_timestamp
        }

        return True, cleaned, None

    def validate_batch(
        self,
        raw_records: List[Dict[str, Any]],
        source: str = "nse_mcp",
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for record in raw_records:
            valid, cleaned, err = self.validate_record(record, source, retrieval_timestamp)
            if valid and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": record, "error": err})

        summary = {
            "total_input": len(raw_records),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejection_errors": [r["error"] for r in rejected[:10]]  # first 10 sample errors
        }

        return accepted, rejected, summary

    def validate_corporate_action(
        self,
        raw: Dict[str, Any],
        symbol: Optional[str] = None,
        source: str = "nse_mcp",
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates a single corporate action event (dividend, split, bonus, rights, etc.).
        Enforces required fields, date formats, valid action types, positive adjustment factor,
        and natural key deduplication (symbol, action_type, ex_date).
        """
        if retrieval_timestamp is None:
            retrieval_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Symbol
        sym = raw.get("symbol") or symbol
        if not sym or not isinstance(sym, str):
            return False, None, "Missing or invalid symbol in corporate action"
        sym = sym.strip().upper()

        # 2. Ex-date
        ex_d = raw.get("exDate") or raw.get("ex_date")
        if not ex_d or not isinstance(ex_d, str):
            return False, None, "Missing or invalid exDate in corporate action"
        try:
            datetime.datetime.strptime(ex_d, "%Y-%m-%d")
        except ValueError:
            return False, None, f"Invalid exDate format: '{ex_d}', expected YYYY-MM-DD"

        # 3. Action type
        act_type = raw.get("actionType") or raw.get("action_type") or "OTHER"
        if not isinstance(act_type, str) or not act_type.strip():
            act_type = "OTHER"
        act_type = act_type.strip().upper()
        if act_type not in self.VALID_ACTION_TYPES:
            # Map known subtypes or default to OTHER
            if "DIVIDEND" in act_type:
                act_type = "DIVIDEND"
            elif "SPLIT" in act_type:
                act_type = "SPLIT"
            elif "BONUS" in act_type:
                act_type = "BONUS"
            elif "RIGHT" in act_type:
                act_type = "RIGHTS"
            else:
                act_type = "OTHER"

        # 4. Purpose
        purpose = raw.get("purpose")
        if purpose is None:
            purpose = f"{act_type} event on {ex_d}"
        purpose = str(purpose).strip()

        # 5. Adjustment factor
        adj_factor_raw = raw.get("adjustmentFactor") if raw.get("adjustmentFactor") is not None else raw.get("adjustment_factor", 1.0)
        try:
            adj_factor = float(adj_factor_raw)
            if adj_factor <= 0.0:
                return False, None, f"Non-positive adjustmentFactor: {adj_factor}"
            # Financial Semantics Safeguard:
            # adjustment_factor is strictly the historical-price scaling multiplier M_hist in (0.0, 1.0] for splits/bonuses.
            # Derivatives/futures market lot multipliers (e.g. 2.0 or 5.0) must never be used as price multipliers.
            if act_type in ("SPLIT", "BONUS") and adj_factor > 1.0:
                return False, None, f"Invalid adjustmentFactor {adj_factor} for {act_type}: historical-price multiplier must be <= 1.0 (derivatives lot multipliers > 1.0 are forbidden)"
        except (ValueError, TypeError) as e:
            return False, None, f"Invalid adjustmentFactor value '{adj_factor_raw}': {e}"

        # 6. Optional dates
        def _parse_opt_date(date_val: Any, field_name: str) -> Tuple[Optional[str], Optional[str]]:
            if not date_val:
                return None, None
            d_str = str(date_val).strip()
            if not d_str:
                return None, None
            try:
                datetime.datetime.strptime(d_str, "%Y-%m-%d")
                return d_str, None
            except ValueError:
                return None, f"Invalid {field_name} format: '{d_str}', expected YYYY-MM-DD"

        rec_d, err_r = _parse_opt_date(raw.get("recordDate") or raw.get("record_date"), "recordDate")
        if err_r:
            return False, None, err_r

        ann_d, err_a = _parse_opt_date(raw.get("announcementDate") or raw.get("announcement_date"), "announcementDate")
        if err_a:
            return False, None, err_a

        eff_d, err_e = _parse_opt_date(raw.get("effectiveDate") or raw.get("effective_date"), "effectiveDate")
        if err_e:
            return False, None, err_e

        # 7. Deduplication check on natural key: (symbol, action_type, ex_date, purpose)
        # Including purpose preserves distinct economic declarations sharing an ex-date (e.g. Final + Special Dividend)
        dedup_key = (sym, act_type, ex_d, purpose)
        if dedup_key in self.seen_ca_keys:
            return False, None, f"Duplicate corporate action for {dedup_key}"
        self.seen_ca_keys.add(dedup_key)

        cleaned: Dict[str, Any] = {
            "symbol": sym,
            "action_type": act_type,
            "ex_date": ex_d,
            "record_date": rec_d,
            "purpose": purpose,
            "adjustment_factor": adj_factor,
            "source": source,
            "retrieval_timestamp": retrieval_timestamp,
            "announcement_date": ann_d,
            "effective_date": eff_d
        }

        return True, cleaned, None

    def validate_corporate_actions_batch(
        self,
        raw_actions: List[Dict[str, Any]],
        symbol: Optional[str] = None,
        source: str = "nse_mcp",
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Validates a batch of corporate action records."""
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for raw_ca in raw_actions:
            valid, cleaned, err = self.validate_corporate_action(
                raw_ca, symbol=symbol, source=source, retrieval_timestamp=retrieval_timestamp
            )
            if valid and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": raw_ca, "error": err})

        summary = {
            "total_input": len(raw_actions),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejection_errors": [r["error"] for r in rejected[:10]]
        }
        return accepted, rejected, summary

    def validate_corporate_disclosure(
        self,
        raw: Dict[str, Any],
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates a corporate disclosure filing.
        Enforces disclosure_id, symbol, ISO broadcast_timestamp, YYYY-MM-DD effective session date,
        governance verification_status, and prevents unverified disclosures from masquerading as verified.
        """
        if retrieval_timestamp is None:
            retrieval_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        disc_id = raw.get("disclosure_id")
        if not disc_id or not isinstance(disc_id, str) or not disc_id.strip():
            return False, None, "Missing or invalid disclosure_id"
        disc_id = disc_id.strip()

        sym = raw.get("symbol")
        if not sym or not isinstance(sym, str) or not sym.strip():
            return False, None, "Missing or invalid symbol in disclosure"
        sym = sym.strip().upper()

        bcast_ts = raw.get("broadcast_timestamp")
        if not bcast_ts or not isinstance(bcast_ts, str) or not bcast_ts.strip():
            return False, None, "Missing broadcast_timestamp"
        # Validate that broadcast timestamp has 'T' or valid ISO structure
        if "T" not in bcast_ts:
            return False, None, f"Invalid ISO broadcast_timestamp format: '{bcast_ts}'"

        eff_session = raw.get("effective_session_date")
        if not eff_session or not isinstance(eff_session, str):
            return False, None, "Missing effective_session_date"
        try:
            datetime.datetime.strptime(eff_session, "%Y-%m-%d")
        except ValueError:
            return False, None, f"Invalid effective_session_date format: '{eff_session}', expected YYYY-MM-DD"

        cat = raw.get("category", "OTHER")
        if not isinstance(cat, str) or not cat.strip():
            cat = "OTHER"
        cat = cat.strip().upper()

        subj = raw.get("subject", "")
        if not isinstance(subj, str):
            subj = str(subj)

        status = raw.get("verification_status") or "PENDING_VERIFICATION"
        status = str(status).strip().upper()
        if status not in self.VALID_VERIFICATION_STATUSES:
            return False, None, f"Invalid verification_status: '{status}', allowed: {sorted(self.VALID_VERIFICATION_STATUSES)}"

        source_url = raw.get("source_url")
        # Governance safety: A VERIFIED disclosure MUST have a documented source URL or official reference
        if status == "VERIFIED":
            if not source_url or not isinstance(source_url, str) or not source_url.strip():
                return False, None, "VERIFIED status requires a non-empty source_url"
            if not (source_url.startswith("http://") or source_url.startswith("https://") or source_url.startswith("file://") or source_url.startswith("urn:")):
                return False, None, f"VERIFIED status requires a valid URI scheme in source_url, got: '{source_url}'"

        # Validate numeric fields if present
        def _parse_opt_float(val: Any, field_name: str, allow_negative: bool = True) -> Tuple[Optional[float], Optional[str]]:
            if val is None or val == "":
                return None, None
            try:
                f_val = float(val)
                if not allow_negative and f_val < 0:
                    return None, f"Field '{field_name}' cannot be negative, got {f_val}"
                return f_val, None
            except (ValueError, TypeError) as e:
                return None, f"Invalid numeric value for '{field_name}': {e}"

        div_dec, err_div = _parse_opt_float(raw.get("dividend_declared"), "dividend_declared", allow_negative=False)
        if err_div:
            return False, None, err_div

        op_margin, err_op = _parse_opt_float(raw.get("operating_margin_pct"), "operating_margin_pct", allow_negative=True)
        if err_op:
            return False, None, err_op

        rev_cr, err_rev = _parse_opt_float(raw.get("revenue_inr_crore"), "revenue_inr_crore", allow_negative=False)
        if err_rev:
            return False, None, err_rev

        rev_yoy_cc, _ = _parse_opt_float(raw.get("revenue_growth_yoy_cc"), "revenue_growth_yoy_cc")
        rev_qoq_cc, _ = _parse_opt_float(raw.get("revenue_growth_qoq_cc"), "revenue_growth_qoq_cc")
        rev_yoy_rep, _ = _parse_opt_float(raw.get("revenue_growth_yoy_reported"), "revenue_growth_yoy_reported")

        # Deduplication check on disclosure_id
        if disc_id in self.seen_disclosure_keys:
            return False, None, f"Duplicate disclosure_id: '{disc_id}'"
        self.seen_disclosure_keys.add(disc_id)

        cleaned: Dict[str, Any] = {
            "disclosure_id": disc_id,
            "symbol": sym,
            "broadcast_timestamp": bcast_ts,
            "effective_session_date": eff_session,
            "category": cat,
            "subject": subj,
            "details_summary": raw.get("details_summary"),
            "source_url": source_url,
            "retrieval_timestamp": retrieval_timestamp,
            "verification_status": status,
            "audit_status": raw.get("audit_status"),
            "dividend_declared": div_dec,
            "operating_margin_pct": op_margin,
            "revenue_inr_crore": rev_cr,
            "revenue_growth_yoy_cc": rev_yoy_cc,
            "revenue_growth_qoq_cc": rev_qoq_cc,
            "revenue_growth_yoy_reported": rev_yoy_rep,
            "source_timestamp_basis": raw.get("source_timestamp_basis")
        }

        return True, cleaned, None

    def validate_corporate_disclosures_batch(
        self,
        raw_disclosures: List[Dict[str, Any]],
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Validates a batch of corporate disclosure records."""
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for raw_d in raw_disclosures:
            valid, cleaned, err = self.validate_corporate_disclosure(raw_d, retrieval_timestamp=retrieval_timestamp)
            if valid and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": raw_d, "error": err})

        summary = {
            "total_input": len(raw_disclosures),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejection_errors": [r["error"] for r in rejected[:10]]
        }
        return accepted, rejected, summary

    def validate_financial_statement(
        self,
        raw: Dict[str, Any],
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates a company financial statement record according to Milestone B4 specifications.
        Enforces:
        - Statement ID & uppercase Symbol.
        - Strict period_type and period_nature (DISCRETE_QUARTER, CUMULATIVE_YTD, ANNUAL).
        - Reporting basis (CONSOLIDATED, STANDALONE) and audit_status.
        - Publication-time provenance (EXACT_EXCHANGE_TIMESTAMP, ANNOUNCEMENT_DATE_VERIFIED, UNKNOWN_UNTIMED).
        - Conservative point-in-time eligibility and effective_session_date assignment.
        - Restatement handling and reason requirement for version > 1.
        - Core accounting consistency (total_revenue >= revenue_operations, shares_outstanding > 0).
        - Natural key deduplication: (symbol, period_end_date, period_type, period_nature, reporting_basis, statement_version).
        """
        if retrieval_timestamp is None:
            retrieval_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        stmt_id = raw.get("statement_id")
        if not stmt_id or not isinstance(stmt_id, str) or not stmt_id.strip():
            return False, None, "Missing or invalid statement_id"
        stmt_id = stmt_id.strip()

        sym = raw.get("symbol")
        if not sym or not isinstance(sym, str) or not sym.strip():
            return False, None, "Missing or invalid symbol in financial statement"
        sym = sym.strip().upper()

        ptype = raw.get("period_type")
        if not ptype or not isinstance(ptype, str) or ptype.strip().upper() not in self.VALID_PERIOD_TYPES:
            return False, None, f"Invalid period_type: '{ptype}', allowed: {sorted(self.VALID_PERIOD_TYPES)}"
        ptype = ptype.strip().upper()

        pnature = raw.get("period_nature")
        if not pnature or not isinstance(pnature, str) or pnature.strip().upper() not in self.VALID_PERIOD_NATURES:
            return False, None, f"Invalid period_nature: '{pnature}', allowed: {sorted(self.VALID_PERIOD_NATURES)}"
        pnature = pnature.strip().upper()

        fyear = raw.get("fiscal_year")
        if not fyear or not isinstance(fyear, str) or not fyear.strip():
            return False, None, "Missing or invalid fiscal_year"
        fyear = fyear.strip().upper()

        fquarter = raw.get("fiscal_quarter")
        if fquarter is not None:
            try:
                fquarter = int(fquarter)
                if fquarter not in (1, 2, 3, 4):
                    return False, None, f"fiscal_quarter must be between 1 and 4, got {fquarter}"
            except (ValueError, TypeError):
                return False, None, f"Invalid fiscal_quarter: '{fquarter}'"

        start_date = raw.get("period_start_date")
        if not start_date or not isinstance(start_date, str):
            return False, None, "Missing or invalid period_start_date"
        try:
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return False, None, f"Invalid period_start_date format: '{start_date}', expected YYYY-MM-DD"

        end_date = raw.get("period_end_date")
        if not end_date or not isinstance(end_date, str):
            return False, None, "Missing or invalid period_end_date"
        try:
            end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return False, None, f"Invalid period_end_date format: '{end_date}', expected YYYY-MM-DD"

        if end_dt < start_dt:
            return False, None, f"period_end_date ({end_date}) precedes period_start_date ({start_date})"

        rep_basis = raw.get("reporting_basis", "CONSOLIDATED")
        if not isinstance(rep_basis, str) or rep_basis.strip().upper() not in self.VALID_REPORTING_BASES:
            return False, None, f"Invalid reporting_basis: '{rep_basis}', allowed: {sorted(self.VALID_REPORTING_BASES)}"
        rep_basis = rep_basis.strip().upper()

        try:
            version = int(raw.get("statement_version", 1))
            if version < 1:
                return False, None, f"statement_version must be >= 1, got {version}"
        except (ValueError, TypeError):
            return False, None, "Invalid statement_version, expected integer"

        audit_status = raw.get("audit_status", "UNAUDITED")
        if not isinstance(audit_status, str) or audit_status.strip().upper() not in self.VALID_AUDIT_STATUSES:
            return False, None, f"Invalid audit_status: '{audit_status}', allowed: {sorted(self.VALID_AUDIT_STATUSES)}"
        audit_status = audit_status.strip().upper()

        # Deduplication check
        dedup_key = (sym, end_date, ptype, pnature, rep_basis, version)
        if dedup_key in self.seen_statement_keys:
            return False, None, f"Duplicate financial statement for natural key: {dedup_key}"

        # Publication-Time Provenance & Availability Policy
        ts_basis = raw.get("source_timestamp_basis", "EXACT_EXCHANGE_TIMESTAMP")
        if not isinstance(ts_basis, str) or ts_basis.strip().upper() not in self.VALID_TIMESTAMP_BASES:
            return False, None, f"Invalid source_timestamp_basis: '{ts_basis}', allowed: {sorted(self.VALID_TIMESTAMP_BASES)}"
        ts_basis = ts_basis.strip().upper()

        pub_date = raw.get("publication_date")
        bcast_ts = raw.get("broadcast_timestamp")
        eff_session = raw.get("effective_session_date")
        pit_eligible = int(raw.get("is_pit_eligible", 1))

        if ts_basis == "UNKNOWN_UNTIMED":
            # Untimed records must never masquerade as verified PIT observations
            pit_eligible = 0
            eff_session = None
        elif ts_basis == "ANNOUNCEMENT_DATE_VERIFIED":
            if not pub_date or not isinstance(pub_date, str):
                return False, None, "ANNOUNCEMENT_DATE_VERIFIED requires valid publication_date"
            try:
                pub_dt = datetime.datetime.strptime(pub_date, "%Y-%m-%d").date()
            except ValueError:
                return False, None, f"Invalid publication_date format: '{pub_date}', expected YYYY-MM-DD"

            # Conservative policy: if effective_session_date not explicitly provided, assign next calendar day (t+1)
            if not eff_session:
                eff_session = (pub_dt + datetime.timedelta(days=1)).isoformat()
            else:
                try:
                    eff_dt = datetime.datetime.strptime(eff_session, "%Y-%m-%d").date()
                    if eff_dt < pub_dt:
                        return False, None, f"effective_session_date ({eff_session}) precedes publication_date ({pub_date})"
                except ValueError:
                    return False, None, f"Invalid effective_session_date format: '{eff_session}'"
        elif ts_basis == "EXACT_EXCHANGE_TIMESTAMP":
            if not bcast_ts or not isinstance(bcast_ts, str) or "T" not in bcast_ts:
                return False, None, f"EXACT_EXCHANGE_TIMESTAMP requires valid ISO broadcast_timestamp with 'T', got: '{bcast_ts}'"
            if not pub_date:
                pub_date = bcast_ts.split("T")[0]
            try:
                pub_dt = datetime.datetime.strptime(pub_date, "%Y-%m-%d").date()
            except ValueError:
                return False, None, f"Invalid publication_date derived from broadcast_timestamp: '{pub_date}'"

            if not eff_session:
                # If timestamp is after 15:30:00 (market close in IST), assign next calendar day; otherwise same day
                time_part = bcast_ts.split("T")[1][:5]
                if time_part >= "15:30":
                    eff_session = (pub_dt + datetime.timedelta(days=1)).isoformat()
                else:
                    eff_session = pub_date

        # Restatement Handling
        is_restated = 1 if (int(raw.get("is_restated", 0)) == 1 or version > 1) else 0
        restatement_reason = raw.get("restatement_reason")
        if is_restated == 1 and (not restatement_reason or not str(restatement_reason).strip()):
            return False, None, f"Restated statement (version {version}) requires a non-empty restatement_reason"

        # Verification Status
        vstatus = raw.get("verification_status", "PENDING_VERIFICATION")
        if not isinstance(vstatus, str) or vstatus.strip().upper() not in self.VALID_VERIFICATION_STATUSES:
            return False, None, f"Invalid verification_status: '{vstatus}'"
        vstatus = vstatus.strip().upper()

        source_url = raw.get("source_url")
        if vstatus == "VERIFIED":
            if not source_url or not isinstance(source_url, str) or not source_url.strip():
                return False, None, "VERIFIED status requires a non-empty source_url"
            if not (source_url.startswith("http://") or source_url.startswith("https://") or source_url.startswith("file://") or source_url.startswith("urn:")):
                return False, None, f"VERIFIED status requires a valid URI scheme in source_url, got: '{source_url}'"

        # Numeric field sanitization
        def _parse_opt_float(val: Any, field_name: str, allow_negative: bool = True) -> Tuple[Optional[float], Optional[str]]:
            if val is None or val == "":
                return None, None
            try:
                f_val = float(val)
                if not allow_negative and f_val < 0:
                    return None, f"Field '{field_name}' cannot be negative, got {f_val}"
                return f_val, None
            except (ValueError, TypeError) as e:
                return None, f"Invalid numeric value for '{field_name}': {e}"

        numeric_fields = [
            ("revenue_operations", True),
            ("other_income", True),
            ("total_revenue", True),
            ("operating_expenses", True),
            ("ebitda", True),
            ("ebit", True),
            ("finance_costs", True),
            ("depreciation_amortization", True),
            ("profit_before_tax", True),
            ("tax_expense", True),
            ("net_profit", True),
            ("basic_eps", True),
            ("diluted_eps", True),
            ("total_equity", True),
            ("total_debt", True),
            ("cash_and_equivalents", True),
            ("total_assets", True),
            ("shares_outstanding", False)
        ]

        cleaned_nums: Dict[str, Optional[float]] = {}
        for fname, allow_neg in numeric_fields:
            val, err = _parse_opt_float(raw.get(fname), fname, allow_negative=allow_neg)
            if err:
                return False, None, err
            cleaned_nums[fname] = val

        # Additional Invariant: total_revenue >= revenue_operations (accounting consistency)
        tot_rev = cleaned_nums.get("total_revenue")
        rev_ops = cleaned_nums.get("revenue_operations")
        if tot_rev is not None and rev_ops is not None:
            if tot_rev < rev_ops - 0.05:
                return False, None, f"total_revenue ({tot_rev}) cannot be less than revenue_operations ({rev_ops})"

        # Additional Invariant: shares_outstanding must be strictly positive if provided
        shs = cleaned_nums.get("shares_outstanding")
        if shs is not None and shs <= 0:
            return False, None, f"shares_outstanding must be strictly positive, got {shs}"

        # Unit normalization for shares_outstanding:
        # Standard: shares_outstanding is stored as the absolute number of equity shares (e.g. 4,150,000,000).
        # If input specifies shares_unit='CRORE', or if shares_unit is omitted and 0 < shs < 100,000 (crore count),
        # convert to absolute shares by multiplying by 10^7.
        shares_unit = str(raw.get("shares_unit", "")).strip().upper()
        if shs is not None and shs > 0:
            if shares_unit == "CRORE" or (not shares_unit and shs < 100000):
                shs = shs * 1e7
            cleaned_nums["shares_outstanding"] = shs

        self.seen_statement_keys.add(dedup_key)

        cleaned: Dict[str, Any] = {
            "statement_id": stmt_id,
            "symbol": sym,
            "period_type": ptype,
            "period_nature": pnature,
            "fiscal_year": fyear,
            "fiscal_quarter": fquarter,
            "period_start_date": start_date,
            "period_end_date": end_date,
            "publication_date": pub_date,
            "broadcast_timestamp": bcast_ts,
            "effective_session_date": eff_session,
            "source_timestamp_basis": ts_basis,
            "is_pit_eligible": pit_eligible,
            "reporting_basis": rep_basis,
            "statement_version": version,
            "audit_status": audit_status,
            "currency": raw.get("currency", "INR"),
            "unit": raw.get("unit", "CRORE"),
            "revenue_operations": cleaned_nums["revenue_operations"],
            "other_income": cleaned_nums["other_income"],
            "total_revenue": cleaned_nums["total_revenue"],
            "operating_expenses": cleaned_nums["operating_expenses"],
            "ebitda": cleaned_nums["ebitda"],
            "ebit": cleaned_nums["ebit"],
            "finance_costs": cleaned_nums["finance_costs"],
            "depreciation_amortization": cleaned_nums["depreciation_amortization"],
            "profit_before_tax": cleaned_nums["profit_before_tax"],
            "tax_expense": cleaned_nums["tax_expense"],
            "net_profit": cleaned_nums["net_profit"],
            "basic_eps": cleaned_nums["basic_eps"],
            "diluted_eps": cleaned_nums["diluted_eps"],
            "total_equity": cleaned_nums["total_equity"],
            "total_debt": cleaned_nums["total_debt"],
            "cash_and_equivalents": cleaned_nums["cash_and_equivalents"],
            "total_assets": cleaned_nums["total_assets"],
            "shares_outstanding": cleaned_nums["shares_outstanding"],
            "source": raw.get("source", "company_filing"),
            "source_url": source_url,
            "retrieval_timestamp": retrieval_timestamp,
            "verification_status": vstatus,
            "is_restated": is_restated,
            "restatement_reason": restatement_reason
        }

        return True, cleaned, None

    def validate_financial_statements_batch(
        self,
        raw_statements: List[Dict[str, Any]],
        retrieval_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Validates a batch of financial statement records."""
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for raw_s in raw_statements:
            valid, cleaned, err = self.validate_financial_statement(raw_s, retrieval_timestamp=retrieval_timestamp)
            if valid and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": raw_s, "error": err})

        summary = {
            "total_input": len(raw_statements),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejection_errors": [r["error"] for r in rejected[:10]]
        }
        return accepted, rejected, summary
