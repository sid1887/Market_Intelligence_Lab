"""
Market Intelligence Lab — Corporate Client (B3.2).

Robust, resilient HTTP client for official National Stock Exchange of India (NSE)
corporate actions and official regulatory disclosures APIs.
Implements cookie warm-up session management, realistic browser headers,
polite pacing, and exponential backoff for HTTP 403 Forbidden and 429 Too Many Requests.
"""

import os
import json
import time
import random
import datetime
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

import requests
from src.config import is_network_allowed


class CorporateClient:
    """
    Session-managed client for official NSE Corporate APIs:
    - Corporate Actions: https://www.nseindia.com/api/corporates-corporateActions
    - Corporate Announcements / Disclosures: https://www.nseindia.com/api/corporate-announcements
    """

    BASE_URL = "https://www.nseindia.com"
    ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateActions"
    ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"

    def __init__(
        self,
        raw_data_dir: str = "data/raw",
        timeout: int = 15,
        delay_seconds: float = 0.6,
        max_retries: int = 5
    ):
        self.raw_data_dir = raw_data_dir
        self.actions_raw_dir = os.path.join(raw_data_dir, "corporate_actions")
        self.disclosures_raw_dir = os.path.join(raw_data_dir, "corporate_disclosures")
        os.makedirs(self.actions_raw_dir, exist_ok=True)
        os.makedirs(self.disclosures_raw_dir, exist_ok=True)

        self.timeout = timeout
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive"
        })
        self._session_initialized = False

    def _init_session(self) -> None:
        """Warms up cookies (AKA_A2, bm_sz, etc.) by making an initial GET to nseindia.com."""
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        try:
            resp = self.session.get(
                self.BASE_URL,
                headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
                timeout=self.timeout
            )
            self._session_initialized = True
        except Exception as e:
            # Re-raise so backoff can retry session initialization
            raise RuntimeError(f"Failed to initialize NSE portal session: {e}")

    def _request_with_retry(
        self,
        url: str,
        params: Dict[str, Any],
        referer: str
    ) -> requests.Response:
        """
        Executes a GET request with exponential backoff on HTTP 403/429 or network glitches.
        Paces requests to avoid triggering Akamai WAF threshold limits.
        """
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        if not self._session_initialized:
            self._init_session()

        headers = {"Referer": referer}
        last_error = None

        for attempt in range(self.max_retries):
            # Enforce pacing delay
            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)

            try:
                resp = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )

                if resp.status_code == 200:
                    return resp

                if resp.status_code in (403, 429):
                    # Edge gateway backoff
                    backoff = min(16.0, (1.0 * (2 ** attempt)) + random.uniform(0.1, 0.6))
                    last_error = f"HTTP {resp.status_code} ({'Forbidden' if resp.status_code == 403 else 'Rate Limited'})"
                    time.sleep(backoff)

                    # On consecutive 403s, refresh session cookies
                    if attempt >= 1:
                        try:
                            self._init_session()
                        except Exception:
                            pass
                    continue

                if resp.status_code == 404:
                    # Endpoint returned 404 (e.g. no data available for symbol)
                    return resp

                # Other HTTP errors (500, 502, 503, 504)
                last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                time.sleep(1.0 + attempt * 0.5)

            except (requests.RequestException, ConnectionError, TimeoutError) as e:
                last_error = str(e)
                time.sleep(1.0 + attempt * 0.5)

        raise RuntimeError(
            f"Failed GET request to {url} with params {params} after {self.max_retries} attempts. Last error: {last_error}"
        )

    def fetch_corporate_actions(self, symbol: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Fetches official declared corporate actions for a symbol from NSE API.
        Saves raw payload and returns (raw_actions_list, raw_file_path).
        """
        params = {"index": "equities", "symbol": symbol}
        referer = "https://www.nseindia.com/companies-listing/corporate-filings-actions"

        resp = self._request_with_retry(self.ACTIONS_URL, params=params, referer=referer)

        raw_actions: List[Dict[str, Any]] = []
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    raw_actions = data
            except json.JSONDecodeError:
                raw_actions = []

        # Archive raw JSON payload
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sanitized_sym = symbol.replace("&", "_AND_")
        raw_path = os.path.join(self.actions_raw_dir, f"{sanitized_sym}_actions_{ts}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": symbol,
                "retrieved_at": ts,
                "endpoint": self.ACTIONS_URL,
                "status_code": resp.status_code,
                "records_count": len(raw_actions),
                "data": raw_actions
            }, f, indent=2)

        return raw_actions, raw_path

    def fetch_corporate_disclosures(self, symbol: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Fetches official board announcements and disclosures for a symbol from NSE API.
        Saves raw payload and returns (raw_announcements_list, raw_file_path).
        """
        params = {"index": "equities", "symbol": symbol}
        referer = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

        resp = self._request_with_retry(self.ANNOUNCEMENTS_URL, params=params, referer=referer)

        raw_disclosures: List[Dict[str, Any]] = []
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    raw_disclosures = data
            except json.JSONDecodeError:
                raw_disclosures = []

        # Archive raw JSON payload
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        sanitized_sym = symbol.replace("&", "_AND_")
        raw_path = os.path.join(self.disclosures_raw_dir, f"{sanitized_sym}_disclosures_{ts}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": symbol,
                "retrieved_at": ts,
                "endpoint": self.ANNOUNCEMENTS_URL,
                "status_code": resp.status_code,
                "records_count": len(raw_disclosures),
                "data": raw_disclosures
            }, f, indent=2)

        return raw_disclosures, raw_path
