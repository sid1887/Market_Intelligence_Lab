"""
Market Intelligence Lab — Real-Time Causal Catalyst & Market Pulse Engine.

Discovers intraday market anomalies (>= 3.0% move or >= 2.5x RVOL),
synthesizes 4-pillar institutional causal attribution:
  - Pillar 1: Price & Structural Memory (52W H/L, 200 SMA, RVOL, Round Numbers)
  - Pillar 2: Sector Basket & Macro Breadth (Sector peers vs Nifty 50)
  - Pillar 3: Corporate Actions & Board Calendar (SEBI filings, dividends, earnings)
  - Pillar 4: Live News Headlines & Market Wire
Persists events to SQLite and broadcasts instant native Web Push notifications.
"""

import os
import json
import logging
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from src.notifications.web_push import broadcast_push

logger = logging.getLogger("tasks.catalyst_engine")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "market_lab.db")
IST = timezone(timedelta(hours=5, minutes=30))


def _get_db() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_catalyst_tables():
    """Initializes the market_catalysts table in SQLite."""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_catalysts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                company_name TEXT,
                sector TEXT,
                move_pct REAL NOT NULL,
                rvol REAL NOT NULL,
                classification TEXT NOT NULL,
                pillar1_price TEXT,
                pillar2_macro TEXT,
                pillar3_corp TEXT,
                pillar4_news TEXT,
                causal_headline TEXT NOT NULL,
                causal_bullets TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                push_sent INTEGER DEFAULT 0
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalysts_symbol ON market_catalysts(symbol);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_catalysts_triggered_at ON market_catalysts(triggered_at);")
        conn.commit()


class CausalCatalystEngine:
    """Intraday anomaly detection and 4-pillar causal market intelligence engine."""

    # In-memory cooldown cache: {symbol: last_investigated_timestamp}
    _cooldowns: Dict[str, datetime] = {}
    COOLDOWN_HOURS = 4

    def __init__(self):
        init_catalyst_tables()

    def get_watchlist_and_priority_symbols(self) -> List[str]:
        """Gathers symbols from active portfolio positions, watchlists, and prominent equities."""
        symbols = set(["RVNL", "NHPC", "TATAMOTORS", "INFY", "RELIANCE", "HDFCBANK", "ITC", "BEL", "SBIN"])
        try:
            with _get_db() as conn:
                # 1. Active portfolio positions
                pos_rows = conn.execute("SELECT DISTINCT symbol FROM portfolio_positions").fetchall()
                for r in pos_rows:
                    if r["symbol"]:
                        symbols.add(r["symbol"])

                # 2. Watchlists
                wl_rows = conn.execute("SELECT DISTINCT symbol FROM user_watchlists").fetchall()
                for r in wl_rows:
                    if r["symbol"]:
                        symbols.add(r["symbol"])

                # 3. Top-50 screener candidates by recent volume / turnover
                top_rows = conn.execute("""
                    SELECT symbol FROM ohlcv_daily
                    WHERE trading_date = (SELECT MAX(trading_date) FROM ohlcv_daily)
                    ORDER BY turnover DESC LIMIT 50
                """).fetchall()
                for r in top_rows:
                    if r["symbol"]:
                        symbols.add(r["symbol"])
        except Exception as e:
            logger.warning(f"Error fetching priority symbols: {e}")

        return sorted(list(symbols))

    def collect_pillar1_price(self, symbol: str) -> Dict[str, Any]:
        """Pillar 1: Price Action, RVOL Surge, 52W Range, 200 SMA, and Psychological Levels."""
        with _get_db() as conn:
            bars = conn.execute("""
                SELECT trading_date, open, high, low, close, prev_close, volume
                FROM ohlcv_daily
                WHERE symbol = ?
                ORDER BY trading_date DESC LIMIT 252
            """, (symbol,)).fetchall()

        if not bars:
            return {
                "latest_price": 0.0,
                "move_pct": 0.0,
                "rvol": 1.0,
                "dist_52w_high_pct": 0.0,
                "dist_52w_low_pct": 0.0,
                "dist_sma200_pct": 0.0,
                "round_level_desc": "Near base level",
            }

        latest = bars[0]
        close = float(latest["close"] or 0.0)
        volume = float(latest["volume"] or 0.0)

        # Calculate move_pct
        if len(bars) > 1 and bars[1]["close"]:
            prev_close = float(bars[1]["close"])
            move_pct = ((close - prev_close) / prev_close) * 100.0
        elif latest["prev_close"]:
            prev_close = float(latest["prev_close"])
            move_pct = ((close - prev_close) / prev_close) * 100.0
        else:
            move_pct = 0.0

        # 20-Day Average Volume & RVOL
        recent_vols = [float(b["volume"] or 0.0) for b in bars[1:21] if b["volume"]]
        avg_vol_20d = sum(recent_vols) / max(1, len(recent_vols)) if recent_vols else volume
        rvol = (volume / avg_vol_20d) if avg_vol_20d > 0 else 1.0

        # 52-Week High & Low
        highs = [float(b["high"] or b["close"]) for b in bars if (b["high"] or b["close"])]
        lows = [float(b["low"] or b["close"]) for b in bars if (b["low"] or b["close"])]
        high_52w = max(highs) if highs else close
        low_52w = min(lows) if lows else close

        dist_52w_high_pct = ((close - high_52w) / high_52w) * 100.0 if high_52w > 0 else 0.0
        dist_52w_low_pct = ((close - low_52w) / low_52w) * 100.0 if low_52w > 0 else 0.0

        # 200 SMA
        closes_200 = [float(b["close"]) for b in bars[:200] if b["close"]]
        sma_200 = sum(closes_200) / len(closes_200) if closes_200 else close
        dist_sma200_pct = ((close - sma_200) / sma_200) * 100.0 if sma_200 > 0 else 0.0

        # Psychological Round Numbers (e.g. ₹100, ₹200, ₹500, ₹1000)
        step = 50.0 if close < 500 else (100.0 if close < 2000 else 500.0)
        nearest_round = round(close / step) * step
        dist_round_pct = ((close - nearest_round) / nearest_round) * 100.0 if nearest_round > 0 else 0.0
        round_desc = f"Testing key psychological milestone at ₹{nearest_round:.0f} ({dist_round_pct:+.1f}%)"

        return {
            "latest_price": round(close, 2),
            "move_pct": round(move_pct, 2),
            "volume": int(volume),
            "avg_vol_20d": int(avg_vol_20d),
            "rvol": round(rvol, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "dist_52w_high_pct": round(dist_52w_high_pct, 1),
            "dist_52w_low_pct": round(dist_52w_low_pct, 1),
            "sma_200": round(sma_200, 2),
            "dist_sma200_pct": round(dist_sma200_pct, 1),
            "round_level_desc": round_desc,
        }

    def collect_pillar2_macro(self, symbol: str, sector: str, move_pct: float) -> Dict[str, Any]:
        """Pillar 2: Sector Basket & Macro Breadth Contagion Analysis."""
        with _get_db() as conn:
            # Get peer symbols in the same sector
            peers = conn.execute("""
                SELECT symbol FROM securities_master
                WHERE sector = ? AND symbol != ? AND is_active = 1
                LIMIT 20
            """, (sector, symbol)).fetchall()
            peer_syms = [p["symbol"] for p in peers]

            peer_moves = []
            if peer_syms:
                placeholders = ",".join(["?"] * len(peer_syms))
                rows = conn.execute(f"""
                    SELECT symbol, close, prev_close FROM ohlcv_daily
                    WHERE symbol IN ({placeholders})
                    AND trading_date = (SELECT MAX(trading_date) FROM ohlcv_daily WHERE symbol = ?)
                """, (*peer_syms, symbol)).fetchall()

                for r in rows:
                    c = float(r["close"] or 0)
                    pc = float(r["prev_close"] or c)
                    if pc > 0:
                        ret = ((c - pc) / pc) * 100.0
                        peer_moves.append(ret)

            # Benchmark Nifty 50 proxy
            nifty_rows = conn.execute("""
                SELECT close FROM index_daily
                WHERE index_name LIKE '%NIFTY 50%'
                ORDER BY trading_date DESC LIMIT 2
            """).fetchall()

            nifty_ret = 0.0
            if len(nifty_rows) >= 2 and nifty_rows[0]["close"] and nifty_rows[1]["close"]:
                nc = float(nifty_rows[0]["close"])
                npc = float(nifty_rows[1]["close"])
                nifty_ret = ((nc - npc) / npc) * 100.0

        sector_mean_ret = sum(peer_moves) / max(1, len(peer_moves)) if peer_moves else 0.0
        advances = sum(1 for m in peer_moves if m > 0.2)
        declines = sum(1 for m in peer_moves if m < -0.2)

        # Classification rule
        is_same_dir = (move_pct > 0 and sector_mean_ret > 0.8) or (move_pct < 0 and sector_mean_ret < -0.8)
        if is_same_dir and abs(sector_mean_ret) >= 1.2:
            classification = "Sector-Wide Basket Momentum"
            alpha_narrative = (
                f"{sector} sector-wide liquidity tide ({sector_mean_ret:+.1f}% avg, {advances} up / {declines} down). "
                f"Correlated beta expansion across peer cohort."
            )
        else:
            classification = "Idiosyncratic Single-Stock Alpha"
            alpha_narrative = (
                f"Isolated idiosyncratic alpha decoupling from {sector} peers ({sector_mean_ret:+.1f}% avg) "
                f"and Nifty 50 ({nifty_ret:+.2f}%). Stock-specific conviction drivers."
            )

        return {
            "sector": sector,
            "sector_mean_ret": round(sector_mean_ret, 2),
            "advances": advances,
            "declines": declines,
            "nifty_ret": round(nifty_ret, 2),
            "classification": classification,
            "alpha_narrative": alpha_narrative,
        }

    def collect_pillar3_corp(self, symbol: str) -> Dict[str, Any]:
        """Pillar 3: Corporate Disclosures, SEBI Filings, Earnings & Board Actions."""
        with _get_db() as conn:
            disclosures = conn.execute("""
                SELECT category, subject, details_summary, broadcast_timestamp
                FROM corporate_disclosures
                WHERE symbol = ?
                ORDER BY broadcast_timestamp DESC LIMIT 3
            """, (symbol,)).fetchall()

            actions = conn.execute("""
                SELECT action_type, ex_date, purpose
                FROM corporate_actions
                WHERE symbol = ?
                ORDER BY ex_date DESC LIMIT 3
            """, (symbol,)).fetchall()

        events = []
        for d in disclosures:
            cat = d["category"] or "FILING"
            subj = d["subject"] or "Corporate Disclosure"
            events.append(f"[{cat}] {subj}")

        for a in actions:
            act = a["action_type"] or "ACTION"
            purp = a["purpose"] or "Corporate Action"
            events.append(f"[{act}] {purp} (Ex-Date: {a['ex_date']})")

        summary = "; ".join(events[:2]) if events else "No pending material board disclosures on exchange wire."
        return {
            "events_count": len(events),
            "events": events[:3],
            "summary": summary,
        }

    def collect_pillar4_news(self, symbol: str, company_name: str, sector: str) -> Dict[str, Any]:
        """Pillar 4: Live RSS & SQLite News Headlines."""
        headlines = []

        # 1. Check local DB news tables
        try:
            with _get_db() as conn:
                rows = conn.execute("""
                    SELECT title, source, published_at FROM equity_news_feed
                    WHERE symbol = ?
                    ORDER BY published_at DESC LIMIT 3
                """, (symbol,)).fetchall()
                for r in rows:
                    if r["title"]:
                        headlines.append(f"{r['title']} ({r['source'] or 'Wire'})")
        except Exception:
            pass

        # 2. If fewer than 2 headlines, fetch live Google News RSS
        if len(headlines) < 2:
            try:
                query = urllib.parse.quote(f"{symbol} NSE {company_name}")
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
                req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0 (compatible; MIL/2.0)"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    root = ET.fromstring(resp.read())
                    for item in root.findall(".//item")[:3]:
                        t = item.find("title")
                        if t is not None and t.text:
                            clean_t = t.text.split(" - ")[0].strip()
                            src = t.text.split(" - ")[-1].strip() if " - " in t.text else "Financial Wire"
                            headlines.append(f"{clean_t} ({src})")
            except Exception as e:
                logger.debug(f"RSS news fetch fallback: {e}")

        top_story = headlines[0] if headlines else f"Institutional flow rotation into {sector} equities."
        return {
            "headlines_count": len(headlines),
            "headlines": headlines[:4],
            "top_story": top_story,
        }

    def synthesize_catalyst(
        self,
        symbol: str,
        company_name: str,
        sector: str,
        p1: Dict[str, Any],
        p2: Dict[str, Any],
        p3: Dict[str, Any],
        p4: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synthesizes the 4 pillars into high-precision institutional causal attribution."""
        direction = "+" if p1["move_pct"] >= 0 else ""
        move_str = f"{direction}{p1['move_pct']:.1f}%"
        rvol_str = f"{p1['rvol']:.1f}x RVOL"

        # Formulate punchy, professional headline
        core_trigger = ""
        if p4["headlines"]:
            # Extract first punchy headline concept
            first_h = p4["headlines"][0].split("(")[0].strip()
            if len(first_h) > 55:
                first_h = first_h[:52] + "..."
            core_trigger = first_h
        elif p3["events"]:
            core_trigger = p3["events"][0]
        else:
            core_trigger = f"Volume Spike ({rvol_str}) · {p2['classification']}"

        causal_headline = f"{symbol} {move_str} · {core_trigger}"

        # 4 Analytical Bullets
        bullets = [
            (
                f"Price & Structural Velocity: Moved {move_str} with {rvol_str} on "
                f"{p1['volume']:,} shares (vs {p1['avg_vol_20d']:,} 20D avg). "
                f"Positioned {p1['dist_52w_high_pct']:+.1f}% from 52W High, {p1['dist_sma200_pct']:+.1f}% vs 200-SMA. "
                f"{p1['round_level_desc']}."
            ),
            (
                f"Macro & Sector Topology: {p2['alpha_narrative']} "
                f"({p2['advances']} peers advancing / {p2['declines']} declining)."
            ),
            (
                f"Corporate Actions & Filings: {p3['summary']}"
            ),
            (
                f"Catalyst Wire & Sentiment: Top development: '{p4['top_story']}'. "
                f"Flow dynamics confirm {p2['classification'].lower()}."
            ),
        ]

        return {
            "symbol": symbol,
            "company_name": company_name,
            "sector": sector,
            "move_pct": p1["move_pct"],
            "rvol": p1["rvol"],
            "classification": p2["classification"],
            "causal_headline": causal_headline,
            "causal_bullets": bullets,
            "pillar1": p1,
            "pillar2": p2,
            "pillar3": p3,
            "pillar4": p4,
        }

    def investigate_symbol(self, symbol: str, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Runs full 4-pillar investigation on a symbol.
        Triggers if abs(move_pct) >= 3.0 or rvol >= 2.5 (or force=True).
        Applies a 4-hour cooldown per symbol to prevent notification spam.
        """
        now = datetime.now(timezone.utc)

        if not force:
            last_run = self._cooldowns.get(symbol)
            if last_run and (now - last_run).total_seconds() < self.COOLDOWN_HOURS * 3600:
                logger.debug(f"{symbol} is under cooldown. Skipping.")
                return None

        # Fetch metadata
        with _get_db() as conn:
            master = conn.execute("""
                SELECT company_name, sector FROM securities_master WHERE symbol = ?
            """, (symbol,)).fetchone()

        company_name = master["company_name"] if master else symbol
        sector = master["sector"] if master else "General"

        p1 = self.collect_pillar1_price(symbol)

        # Anomaly trigger check
        is_anomaly = abs(p1["move_pct"]) >= 3.0 or p1["rvol"] >= 2.5
        if not is_anomaly and not force:
            return None

        p2 = self.collect_pillar2_macro(symbol, sector, p1["move_pct"])
        p3 = self.collect_pillar3_corp(symbol)
        p4 = self.collect_pillar4_news(symbol, company_name, sector)

        synth = self.synthesize_catalyst(symbol, company_name, sector, p1, p2, p3, p4)

        # Persist event to SQLite
        now_iso = now.isoformat()
        with _get_db() as conn:
            cur = conn.execute("""
                INSERT INTO market_catalysts (
                    symbol, company_name, sector, move_pct, rvol, classification,
                    pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                    causal_headline, causal_bullets, triggered_at, push_sent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                symbol,
                company_name,
                sector,
                p1["move_pct"],
                p1["rvol"],
                p2["classification"],
                json.dumps(p1),
                json.dumps(p2),
                json.dumps(p3),
                json.dumps(p4),
                synth["causal_headline"],
                json.dumps(synth["causal_bullets"]),
                now_iso,
            ))
            conn.commit()
            catalyst_id = cur.lastrowid

        synth["id"] = catalyst_id
        synth["triggered_at"] = now_iso
        self._cooldowns[symbol] = now

        # Broadcast Web Push Notification to mobile & desktop subscribers
        push_body = synth["causal_bullets"][0][:140] + "..." if synth["causal_bullets"] else synth["causal_headline"]
        broadcast_push(
            title=synth["causal_headline"],
            body=push_body,
            url=f"/stocks/{symbol}",
            tag=f"catalyst-{symbol}-{int(now.timestamp())}"
        )

        logger.info(f"Catalyst synthesized and dispatched for {symbol}: {synth['causal_headline']}")
        return synth

    def run_intraday_scan(self, force_symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Scans universe for anomalies and returns any newly synthesized catalysts."""
        if force_symbol:
            res = self.investigate_symbol(force_symbol, force=True)
            return [res] if res else []

        symbols = self.get_watchlist_and_priority_symbols()
        results = []
        for sym in symbols:
            cat = self.investigate_symbol(sym, force=False)
            if cat:
                results.append(cat)

        return results

    @staticmethod
    def get_live_catalysts(limit: int = 20) -> List[Dict[str, Any]]:
        """Fetches recent catalysts from SQLite for frontend pulse feeds."""
        init_catalyst_tables()
        with _get_db() as conn:
            rows = conn.execute("""
                SELECT id, symbol, company_name, sector, move_pct, rvol, classification,
                       pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                       causal_headline, causal_bullets, triggered_at
                FROM market_catalysts
                ORDER BY triggered_at DESC LIMIT ?
            """, (limit,)).fetchall()

            out = []
            for r in rows:
                item = dict(r)
                try:
                    item["causal_bullets"] = json.loads(item["causal_bullets"])
                except Exception:
                    item["causal_bullets"] = []
                try:
                    item["pillar1"] = json.loads(item.get("pillar1_price") or "{}")
                    item["pillar2"] = json.loads(item.get("pillar2_macro") or "{}")
                    item["pillar3"] = json.loads(item.get("pillar3_corp") or "{}")
                    item["pillar4"] = json.loads(item.get("pillar4_news") or "{}")
                except Exception:
                    pass
                out.append(item)
            return out


# Singleton instance
catalyst_engine = CausalCatalystEngine()
