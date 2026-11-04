import unittest
import os
from src.client.nse_mcp_client import NseMcpClient

class TestNseMcpIntegration(unittest.TestCase):
    """
    [LIVE API INTEGRATION TEST]
    Directly tests connectivity, tool negotiation, and response structures from the
    official National Stock Exchange of India (NSE) Model Context Protocol server.
    """

    @classmethod
    def setUpClass(cls):
        if os.environ.get("RUN_LIVE_TESTS") != "1":
            raise unittest.SkipTest("Live network integration tests disabled by default. Set RUN_LIVE_TESTS=1 to run.")
        cls.client = NseMcpClient(
            endpoint="https://mcp.nseindia.in/bhavcopy/cm/mcp",
            timeout_seconds=12,
            max_affinity_retries=6,
            max_reinit_attempts=3
        )

    @unittest.skipUnless(os.environ.get("RUN_LIVE_TESTS") == "1", "Live network integration tests disabled by default. Set RUN_LIVE_TESTS=1 to run.")
    def test_live_mcp_initialize_and_tool_call(self):
        # 1. Initialize
        sid = self.client.initialize()
        self.assertIsNotNone(sid)
        self.assertTrue(len(sid) > 10, f"Expected valid UUID session ID, got: {sid}")

        # 2. Call live tool: get_52_week_high_low for INFY
        data, raw = self.client.call_tool("get_52_week_high_low", {"symbol": "INFY"})
        self.assertIsNotNone(data, "Live NSE MCP tool returned null data")
        self.assertIn("symbol", data)
        self.assertEqual(data["symbol"], "INFY")
        self.assertIn("52w_high", data)
        self.assertIn("52w_low", data)
        print(f"\n[LIVE INTEGRATION VERIFIED] INFY 52w High: ₹{data.get('52w_high')} | 52w Low: ₹{data.get('52w_low')} | Position: {data.get('position_in_range_pct')}%")

if __name__ == "__main__":
    unittest.main()
