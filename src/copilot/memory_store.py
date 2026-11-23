"""
src/copilot/memory_store.py
Conversational Episodic Memory & Rule Distillation Engine for Copilot.

Stores and retrieves compact, PII-free episodic memories:
1. User-specific trading rules & execution preferences (e.g., post-10:30 AM entries).
2. Ticker theses and trade reviews (e.g., RVNL momentum breakdown exit, GAIL accumulation).
3. Risk limits and sizing discipline.
Auto-pruned to the latest 500 records to maintain zero disk/memory bloat.
"""

import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.CopilotMemory")

MAX_EPISODES = 500


def sanitize_conversational_pii(text: str) -> str:
    """Strips PAN, phone numbers, emails, and client codes from memory text."""
    if not text:
        return ""
    sanitized = re.sub(r"[A-Z]{5}[0-9]{4}[A-Z]", "[PAN_REDACTED]", text)
    sanitized = re.sub(r"[6-9]\d{9}", "[PHONE_REDACTED]", sanitized)
    sanitized = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)\b(angel|client|ucc)[_\s]*[a-z0-9]{5,}\b", "[CLIENT_ID_REDACTED]", sanitized)
    return sanitized.strip()


class CopilotMemoryStore:
    """
    Persistent conversational episodic memory store backed by SQLite.
    Provides cross-session continuity without requiring heavy vector databases.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._init_db()

    def _init_db(self) -> None:
        """Initializes memory table and covering indexes."""
        with self.db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS copilot_memory_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    symbols_csv TEXT NOT NULL,
                    category TEXT NOT NULL, -- 'THESIS', 'TRADE_REVIEW', 'RISK_RULE', 'PREFERENCE'
                    summary_text TEXT NOT NULL,
                    outcome_status TEXT DEFAULT 'ACTIVE',
                    importance_score REAL DEFAULT 1.0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_symbols ON copilot_memory_episodes(symbols_csv)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_created ON copilot_memory_episodes(created_at DESC)")
            conn.commit()

    def _sanitize_pii(self, text: str) -> str:
        """Strips PAN, phone numbers, emails, and client codes from memory text."""
        return sanitize_conversational_pii(text)

    def _prune_episodes(self) -> None:
        """Keeps SQLite compact by pruning to the latest 500 episodes."""
        with self.db.get_connection() as conn:
            conn.execute(f"""
                DELETE FROM copilot_memory_episodes
                WHERE id NOT IN (
                    SELECT id FROM copilot_memory_episodes
                    ORDER BY id DESC
                    LIMIT {MAX_EPISODES}
                )
            """)
            conn.commit()

    def record_episode(
        self,
        symbols: List[str],
        category: str,
        summary_text: str,
        outcome_status: str = "ACTIVE",
        importance_score: float = 1.0,
    ) -> int:
        """Records a new sanitized episodic memory entry."""
        symbols_clean = ",".join(sorted(set(s.strip().upper() for s in symbols if s.strip())))
        clean_text = self._sanitize_pii(summary_text)

        with self.db.get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO copilot_memory_episodes (
                    symbols_csv, category, summary_text, outcome_status, importance_score
                ) VALUES (?, ?, ?, ?, ?)
            """, (symbols_clean or "GLOBAL", category.upper(), clean_text, outcome_status.upper(), float(importance_score)))
            conn.commit()
            episode_id = cur.lastrowid or 0

        # Auto-prune periodically
        if episode_id % 25 == 0:
            self._prune_episodes()

        return episode_id

    def distill_and_record_turn(
        self,
        user_prompt: str,
        symbol: Optional[str] = None,
        assistant_response: Optional[str] = None,
        primary_symbol: Optional[str] = None,
        copilot_response: Optional[str] = None,
    ) -> Optional[int]:
        """
        Extracts salient trading rules, preferences, or stock theses from a completed turn
        without requiring an expensive secondary LLM call.
        """
        sym = symbol or primary_symbol or "GLOBAL"
        resp = assistant_response or copilot_response or ""
        p_lower = user_prompt.lower()
        sym_clean = sym.strip().upper()

        # 1. User timing / execution preference
        if any(w in p_lower for w in ("10:30", "entry time", "morning", "open high", "pre-market", "timing")):
            text = f"User preference on {sym_clean}: Entry timing and opening volatility discipline ({user_prompt[:90]})."
            return self.record_episode([sym_clean], "PREFERENCE", text, importance_score=1.5)

        # 2. Risk rule / sizing constraint
        if any(w in p_lower for w in ("max size", "stop loss", "cooldown", "budget", "risk rule", "1500", "2000")):
            text = f"Risk parameter discussed on {sym_clean}: User queried sizing/risk limits ({user_prompt[:90]})."
            return self.record_episode([sym_clean], "RISK_RULE", text, importance_score=1.3)

        # 3. Specific stock thesis / decision review
        if sym_clean and sym_clean not in ("NIFTY 50", "GLOBAL", "NIFTY"):
            # Extract first sentence of assistant verdict as thesis takeaway
            first_sentence = resp.split(".")[0].strip() if resp else ""
            if len(first_sentence) > 15:
                text = f"{sym_clean} Thesis Review: User asked '{user_prompt[:70]}...'. Deliberation verdict: {first_sentence[:120]}."
                return self.record_episode([sym_clean], "THESIS", text, importance_score=1.1)

        return None

    def retrieve_relevant_episodes(
        self,
        symbols: List[str],
        user_query: str = "",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant episodes matching active symbols or prompt keywords.
        """
        target_syms = [s.strip().upper() for s in symbols if s.strip() and s.strip().upper() != "GLOBAL"]
        q_words = [w.strip().lower() for w in re.findall(r"\w+", user_query) if len(w) > 3]

        results: List[Dict[str, Any]] = []
        with self.db.get_connection() as conn:
            # 1. Exact symbol match
            if target_syms:
                placeholders = ",".join("?" for _ in target_syms)
                sym_conditions = " OR ".join(f"symbols_csv LIKE ?" for _ in target_syms)
                params = [f"%{s}%" for s in target_syms]
                rows = conn.execute(f"""
                    SELECT id, created_at, symbols_csv, category, summary_text, outcome_status, importance_score
                    FROM copilot_memory_episodes
                    WHERE {sym_conditions}
                    ORDER BY importance_score DESC, id DESC
                    LIMIT {limit}
                """, params).fetchall()
                results.extend(dict(r) for r in rows)

            # 2. Keyword & Risk rule fallback if under limit
            if len(results) < limit:
                needed = limit - len(results)
                existing_ids = [r["id"] for r in results]
                id_filter = f"AND id NOT IN ({','.join(str(i) for i in existing_ids)})" if existing_ids else ""

                rule_rows = conn.execute(f"""
                    SELECT id, created_at, symbols_csv, category, summary_text, outcome_status, importance_score
                    FROM copilot_memory_episodes
                    WHERE category IN ('RISK_RULE', 'PREFERENCE') {id_filter}
                    ORDER BY importance_score DESC, id DESC
                    LIMIT {needed}
                """).fetchall()
                results.extend(dict(r) for r in rule_rows)

        for res in results:
            res["primary_symbol"] = res["symbols_csv"].split(",")[0] if res.get("symbols_csv") else ""

        return results[:limit]

    def format_episodes_for_prompt(self, episodes: List[Dict[str, Any]]) -> str:
        """Formats retrieved episodes into an LLM context block."""
        if not episodes:
            return ""

        lines = ["[CONVERSATIONAL EPISODIC MEMORY (RELEVANT PAST THESES & RULES)]"]
        for ep in episodes:
            lines.append(f"- [{ep['category']}] ({ep['symbols_csv']}): {ep['summary_text']}")
        return "\n".join(lines)
