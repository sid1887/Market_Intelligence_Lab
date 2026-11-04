import requests
import json
import time
import os
import datetime
from typing import Dict, Any, List, Optional, Tuple
from src.config import is_network_allowed

class NseMcpClient:
    """
    Robust streamable-HTTP client for the official National Stock Exchange (NSE)
    Bhavcopy and Capital Market Model Context Protocol (MCP) servers.
    Handles Akamai multi-node session affinity, automatic re-initialization,
    chunked pagination, and raw payload archival.
    """

    def __init__(
        self,
        endpoint: str = "https://mcp.nseindia.in/bhavcopy/cm/mcp",
        timeout_seconds: int = 12,
        max_affinity_retries: int = 6,
        max_reinit_attempts: int = 3,
        raw_data_dir: str = "data/raw"
    ):
        self.endpoint = endpoint
        self.timeout = timeout_seconds
        self.max_affinity_retries = max_affinity_retries
        self.max_reinit_attempts = max_reinit_attempts
        self.raw_data_dir = raw_data_dir
        os.makedirs(self.raw_data_dir, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        })
        self.session_id: Optional[str] = None

    def initialize(self) -> str:
        """Sends JSON-RPC initialize payload to establish a session with an MCP node."""
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "MarketIntelligenceLab",
                    "version": "0.1.0"
                }
            }
        }
        resp = self.session.post(self.endpoint, json=init_payload, timeout=self.timeout)
        resp.raise_for_status()

        sid = resp.headers.get("Mcp-Session-Id")
        if not sid:
            raise RuntimeError("NSE MCP server did not return an Mcp-Session-Id header.")

        self.session_id = sid
        self.session.headers["mcp-session-id"] = self.session_id
        return self.session_id

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Calls a tool on the NSE MCP server with bounded retries for Akamai session affinity.
        Returns (parsed_data, raw_json_rpc_response).
        """
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000) % 1000000,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        last_error = None
        for reinit_idx in range(self.max_reinit_attempts):
            if not self.session_id:
                self.initialize()

            for affinity_idx in range(self.max_affinity_retries):
                try:
                    resp = self.session.post(self.endpoint, json=payload, timeout=self.timeout)
                    if resp.status_code == 200:
                        raw_text = resp.text
                        for line in raw_text.splitlines():
                            if line.startswith("data:"):
                                json_data = json.loads(line[5:])
                                content_list = json_data.get("result", {}).get("content", [])
                                if not content_list:
                                    return None, json_data

                                text_content = content_list[0].get("text", "")
                                try:
                                    parsed = json.loads(text_content)
                                except json.JSONDecodeError:
                                    parsed = text_content
                                return parsed, json_data

                    elif resp.status_code == 404:
                        # Akamai routed to a node missing this in-memory session. Retry affinity.
                        last_error = f"Session affinity miss (HTTP 404) on node. Retry {affinity_idx + 1}/{self.max_affinity_retries}"
                        time.sleep(0.2 * (affinity_idx + 1))
                        continue
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        time.sleep(0.3)
                except Exception as e:
                    last_error = f"Network or decoding exception: {e}"
                    time.sleep(0.3)

            # Invalidate session and re-initialize if affinity retries exhausted
            self.session_id = None

        raise RuntimeError(f"Failed to execute MCP tool '{tool_name}' after {self.max_reinit_attempts} session re-inits. Last error: {last_error}")

    def fetch_stock_history_chunked(
        self,
        symbol: str,
        total_months: int = 12,
        end_date: str = "today"
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Paginates backwards in 3-month slices to retrieve the requested duration of daily data.
        Returns (combined_raw_records, raw_backup_file_path).
        """
        records_by_date: Dict[str, Dict[str, Any]] = {}
        curr_end = end_date
        chunks_needed = (total_months + 2) // 3
        all_chunk_payloads = []

        for chunk_idx in range(chunks_needed):
            chunk_data, raw_resp = self.call_tool(
                "get_stock_history",
                {"symbol": symbol, "months": 3, "endDate": curr_end}
            )
            all_chunk_payloads.append(raw_resp)

            if not isinstance(chunk_data, dict):
                break

            data_list = chunk_data.get("data", [])
            if not data_list:
                break

            for rec in data_list:
                d = rec.get("date")
                if d:
                    records_by_date[d] = rec

            earliest_in_chunk = chunk_data.get("from_date")
            if not earliest_in_chunk or earliest_in_chunk == curr_end:
                break

            # Move boundary back one day
            try:
                earliest_dt = datetime.datetime.strptime(earliest_in_chunk, "%Y-%m-%d")
                prev_day = (earliest_dt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                curr_end = prev_day
            except Exception:
                curr_end = earliest_in_chunk

        # Sort chronologically
        sorted_dates = sorted(records_by_date.keys())
        combined_records = [records_by_date[d] for d in sorted_dates]

        # Save raw payload backup
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_path = os.path.join(self.raw_data_dir, f"{symbol}_history_{ts}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": symbol,
                "requested_months": total_months,
                "retrieved_at": ts,
                "chunks": all_chunk_payloads,
                "combined_records_count": len(combined_records)
            }, f, indent=2)

        return combined_records, raw_path

    def fetch_corporate_actions(
        self,
        symbol: str,
        from_date: str,
        to_date: str
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Fetches official corporate actions (dividends, splits, bonuses, rights)."""
        # Upstream NSE corporate actions endpoint treats unencoded '&' as query separator.
        # Encode '&' as '%26' so symbols like 'M&M' resolve accurately.
        query_sym = symbol.replace("&", "%26")
        data, raw_resp = self.call_tool(
            "get_corporate_actions",
            {"symbol": query_sym, "fromDate": from_date, "toDate": to_date}
        )

        actions: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            actions = data.get("actions", [])

        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_path = os.path.join(self.raw_data_dir, f"{symbol}_corporate_actions_{ts}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": symbol,
                "from_date": from_date,
                "to_date": to_date,
                "retrieved_at": ts,
                "payload": raw_resp
            }, f, indent=2)

        return actions, raw_path
