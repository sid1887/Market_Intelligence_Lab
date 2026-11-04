"""
Market Intelligence Lab — Offline Governance & Return Continuity Hardening Suite.

Verifies strict fail-closed network policies and consecutive-session return continuity:
1. UniverseManager never calls urlopen() when offline, reading local cache directly.
2. UniverseManager fails closed with RuntimeError when offline and cache is missing.
3. NseMcpClient.call_tool() is blocked even when an active session_id is pre-populated.
4. Default test discovery suite executes with zero attempted outbound network calls.
5. Benchmark and synthetic peer returns reject non-consecutive observation pairs.
"""
import os
import tempfile
import unittest
import urllib.request
import socket
from unittest.mock import patch, MagicMock

from src.config import is_network_allowed
from src.client.universe_manager import UniverseManager
from src.client.nse_mcp_client import NseMcpClient
from src.storage.database import DatabaseManager
from src.quant.movement_analyzer import MarketMovementAnalyzer


class TestOfflineGovernanceHardening(unittest.TestCase):
    """Exhaustive tests for offline boundary enforcement and return continuity."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "data/market_lab.db"
        cls.db = DatabaseManager(cls.db_path)

    def test_01_universe_manager_never_calls_urlopen_when_offline(self):
        """
        Priority 0.1: UniverseManager must read local cache directly without
        calling urllib.request.urlopen() when offline_mode is True.
        """
        self.assertFalse(is_network_allowed(), "Precondition failed: network must be disallowed.")

        um = UniverseManager(self.db, cache_dir="data/universe")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = AssertionError("NETWORK VIOLATION: urlopen was called while offline!")
            constituents = um.fetch_current_nifty50_constituents()

            self.assertEqual(len(constituents), 50)
            mock_urlopen.assert_not_called()

    def test_02_universe_manager_fails_closed_when_cache_missing(self):
        """
        Priority 0.1: UniverseManager must fail closed (raise RuntimeError)
        when offline and the local cache CSV is missing, without attempting network calls.
        """
        self.assertFalse(is_network_allowed())

        with tempfile.TemporaryDirectory() as empty_dir:
            um = UniverseManager(self.db, cache_dir=empty_dir)

            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = AssertionError("NETWORK VIOLATION: urlopen was called while offline!")

                with self.assertRaises(RuntimeError) as ctx:
                    um.fetch_current_nifty50_constituents()

                self.assertIn("Network access disabled", str(ctx.exception))
                self.assertIn("missing", str(ctx.exception).lower())
                mock_urlopen.assert_not_called()

    def test_03_nse_mcp_client_call_tool_blocked_with_existing_session(self):
        """
        Priority 0.2: NseMcpClient.call_tool() must check network policy at the start
        and fail closed even if an active session_id is already present.
        """
        self.assertFalse(is_network_allowed())

        client = NseMcpClient(
            endpoint="https://mcp.nseindia.in/bhavcopy/cm/mcp",
            timeout_seconds=5
        )
        # Pre-populate session_id to simulate an existing Akamai session
        client.session_id = "pre-existing-akamai-session-uuid"

        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = AssertionError("NETWORK VIOLATION: session.post was called while offline!")

            with self.assertRaises(RuntimeError) as ctx:
                client.call_tool("get_stock_history", {"symbol": "INFY"})

            self.assertIn("Network access disabled", str(ctx.exception))
            mock_post.assert_not_called()

    def test_04_default_test_discovery_suite_performs_zero_attempted_network_calls(self):
        """
        Priority 2.4: Proves that executing representative operational code paths
        under a hard socket connect & urlopen interceptor performs zero attempted network calls.
        """
        network_attempts = []

        orig_connect = socket.socket.connect
        orig_urlopen = urllib.request.urlopen

        def intercept_connect(sock_self, *args, **kwargs):
            network_attempts.append(("socket.connect", args))
            raise AssertionError(f"Intercepted socket connect: {args}")

        def intercept_urlopen(*args, **kwargs):
            network_attempts.append(("urllib.urlopen", args))
            raise AssertionError(f"Intercepted urlopen: {args}")

        with patch("socket.socket.connect", side_effect=intercept_connect):
            with patch("urllib.request.urlopen", side_effect=intercept_urlopen):
                # 1. UniverseManager
                um = UniverseManager(self.db, cache_dir="data/universe")
                c = um.fetch_current_nifty50_constituents()
                self.assertEqual(len(c), 50)

                # 2. Movement Analyzer
                analyzer = MarketMovementAnalyzer(self.db)
                mv = analyzer.analyze_session_movement("INFY", "2026-10-16")
                self.assertEqual(mv.symbol, "INFY")

        self.assertEqual(
            len(network_attempts), 0,
            f"Expected 0 network attempts, but intercepted {len(network_attempts)}: {network_attempts}"
        )

    def test_05_benchmark_and_synthetic_peer_returns_reject_non_consecutive_pairs(self):
        """
        Priority 1: Target-date benchmark, official sector, and synthetic peer returns
        must strictly reject non-consecutive observation pairs (where intermediate
        exchange trading sessions occurred).
        """
        # 1. Broad-market benchmark calendar gap rejection
        mock_db_bm = MagicMock(wraps=self.db)
        # Provide NIFTY 50 PRI with a calendar gap: 2026-10-23 to 2026-10-27 (missing active Oct 26)
        mock_db_bm.get_index_history.return_value = [
            {"trading_date": "2026-10-23", "close": 24000.0},
            {"trading_date": "2026-10-27", "close": 24100.0}
        ]
        analyzer_bm = MarketMovementAnalyzer(mock_db_bm)
        res_bm = analyzer_bm.analyze_session_movement("INFY", "2026-10-27")
        self.assertIsNone(
            res_bm.benchmark_return,
            "Benchmark return must be None when index observation spans missing exchange sessions."
        )

        # 2. Synthetic peer calendar gap rejection
        mock_db_peer = MagicMock(wraps=self.db)

        # Peer TCS has a calendar gap from 2026-10-23 to 2026-10-27 (missing Oct 26)
        def mock_stock_history(sym):
            if sym == "TCS":
                return [
                    {"trading_date": "2026-10-23", "close": 4000.0, "open": 4000.0, "high": 4010.0, "low": 3990.0, "volume": 1000},
                    {"trading_date": "2026-10-27", "close": 4050.0, "open": 4010.0, "high": 4060.0, "low": 4000.0, "volume": 1000}
                ]
            return self.db.get_stock_history(sym)

        mock_db_peer.get_stock_history.side_effect = mock_stock_history
        analyzer_peer = MarketMovementAnalyzer(mock_db_peer)
        res_peer = analyzer_peer.analyze_session_movement("RELIANCE", "2026-10-27")

        # TCS must be purged from peer_returns due to non-consecutive observation
        self.assertNotIn(
            "TCS", res_peer.peer_returns,
            "Peer TCS must be excluded from synthetic peer basket when observation spans missing sessions."
        )


if __name__ == "__main__":
    unittest.main()
