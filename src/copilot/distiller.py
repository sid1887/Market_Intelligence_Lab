"""
src/copilot/distiller.py
Teacher-Student Knowledge Distillation Engine for Market Intelligence Lab Copilot.
Abstracts high-conviction Groq/Gemini Teacher completions into generalized quantitative
reasoning templates, parameterizes entity/price slots, trains local TF-IDF + Ridge
regressors (< 2MB artifact), and hydrates offline responses in < 2ms without LLM API calls.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics.pairwise import cosine_similarity

from src.storage.database import DatabaseManager

logger = logging.getLogger("copilot.distiller")

DEFAULT_MODEL_PATH = "data/models/copilot_distilled.joblib"
DEFAULT_META_PATH = "data/models/copilot_distilled_meta.json"

CANONICAL_SLOTS = [
    "{{SYMBOL}}",
    "{{COMPANY_NAME}}",
    "{{PRICE}}",
    "{{SMA200}}",
    "{{RET20D}}",
    "{{ROE}}",
    "{{PE}}",
    "{{ML_20D_RET}}",
    "{{ML_20D_BPS}}",
    "{{TARGET_20D}}",
    "{{FLOOR_20D}}",
    "{{HIGH_52W}}",
    "{{LOW_52W}}",
]


def abstract_prompt_text(prompt: str, symbol: str, company_name: Optional[str] = None) -> str:
    """Replaces concrete ticker references in user prompt with canonical {{SYMBOL}} placeholder."""
    out = prompt
    if symbol:
        out = re.sub(rf"\b{re.escape(symbol)}\b", "{{SYMBOL}}", out, flags=re.IGNORECASE)
    if company_name and len(company_name) > 3:
        out = re.sub(rf"\b{re.escape(company_name)}\b", "{{COMPANY_NAME}}", out, flags=re.IGNORECASE)
    return out.strip()


def abstract_teacher_response(
    response: str,
    symbol: str,
    company_name: Optional[Any] = None,
    grounded_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Parameterizes ticker-specific figures, prices, and ratios into canonical template slots.
    """
    if isinstance(company_name, dict) and grounded_data is None:
        grounded_data = company_name
        company_name = grounded_data.get("company_name")

    grounded_data = grounded_data or {}
    template = response

    # 1. Company Name & Symbol
    if company_name and isinstance(company_name, str) and len(company_name) > 3:
        template = re.sub(rf"\b{re.escape(company_name)}\b", "{{COMPANY_NAME}}", template, flags=re.IGNORECASE)
    if symbol:
        template = re.sub(rf"\b{re.escape(symbol)}\b", "{{SYMBOL}}", template, flags=re.IGNORECASE)

    # 2. Extract numeric values from grounded telemetry
    price = grounded_data.get("current_price") or grounded_data.get("latest_close")
    tech = grounded_data.get("technicals", {})
    fund = grounded_data.get("fundamentals", {})
    draw = grounded_data.get("historical_drawdowns", {})
    ml = grounded_data.get("ml_forecast", {})
    fc_20 = ml.get("forecasts", {}).get("20D", {})

    sma200 = tech.get("sma_200")
    ret20d = tech.get("ret_20d_pct")
    roe = fund.get("roe_pct")
    pe = fund.get("ttm_pe") or fund.get("pe_ratio")
    ml_ret = fc_20.get("expected_return_pct")
    ml_bps = fc_20.get("expected_excess_bps")

    h52 = draw.get("high_52w", {}).get("price")
    l52 = draw.get("low_52w", {}).get("price")

    target = grounded_data.get("target_price") or (round(price * 1.05, 2) if price else None)
    floor = grounded_data.get("stop_loss") or (round(price * 0.95, 2) if price else None)

    # Substitute prices with currency prefix
    def replace_val(pattern_val: Optional[float], slot: str, is_pct: bool = False, is_curr: bool = False):
        nonlocal template
        if pattern_val is None:
            return
        # Match both raw number and formatted string
        if is_curr:
            # Matches ₹1,234.50 or ₹1234.50 or 1,234.50
            curr_regex = rf"(?:₹\s*|\b){re.escape(f'{pattern_val:,.2f}')}\b|(?:₹\s*|\b){re.escape(f'{pattern_val:.2f}')}\b"
            template = re.sub(curr_regex, slot, template)
        elif is_pct:
            pct_regex = rf"{re.escape(f'{pattern_val:+.2f}%')}|{re.escape(f'{pattern_val:.2f}%')}|{re.escape(f'{pattern_val:.1f}%')}"
            template = re.sub(pct_regex, slot, template)
        else:
            val_regex = rf"\b{re.escape(f'{pattern_val:.2f}')}\b|\b{re.escape(f'{pattern_val:.1f}')}\b"
            template = re.sub(val_regex, slot, template)

    replace_val(price, "{{PRICE}}", is_curr=True)
    replace_val(target, "{{TARGET_20D}}", is_curr=True)
    replace_val(floor, "{{FLOOR_20D}}", is_curr=True)
    replace_val(sma200, "{{SMA200}}", is_curr=True)
    replace_val(h52, "{{HIGH_52W}}", is_curr=True)
    replace_val(l52, "{{LOW_52W}}", is_curr=True)

    replace_val(ret20d, "{{RET20D}}", is_pct=True)
    replace_val(ml_ret, "{{ML_20D_RET}}", is_pct=True)
    replace_val(ml_bps, "{{ML_20D_BPS}}")
    replace_val(roe, "{{ROE}}", is_pct=True)

    if pe is not None:
        template = re.sub(rf"{pe:.1f}x|{pe:.2f}x", "{{PE}}", template)

    return template


def store_teacher_trace(
    db: Optional[DatabaseManager] = None,
    intent: str = "DIRECT_QA",
    symbol: str = "NIFTY 50",
    user_prompt: str = "",
    teacher_model: str = "groq:openai/gpt-oss-120b",
    teacher_response: str = "",
    grounded_data: Optional[Dict[str, Any]] = None,
    tokens_total: int = 0,
    sector: Optional[str] = None,
    db_manager: Optional[DatabaseManager] = None,
    telemetry_features: Optional[Dict[str, Any]] = None,
    **kwargs
) -> bool:
    """
    Stores an abstracted teacher execution trace in copilot_distillation_corpus.
    Maintains a maximum 2,000 trace ceiling with deduplication.
    """
    if not teacher_response or len(teacher_response.strip()) < 60:
        return False

    target_db = db or db_manager
    if target_db is None:
        target_db = DatabaseManager()

    data = grounded_data or telemetry_features or {}
    comp_name = data.get("company_name", symbol)
    abstracted_prompt = abstract_prompt_text(user_prompt, symbol, comp_name)
    abstracted_template = abstract_teacher_response(teacher_response, symbol, comp_name, data)

    tech = data.get("technicals", {})
    fund = data.get("fundamentals", {})
    ml = data.get("ml_forecast", {})
    fc_20 = ml.get("forecasts", {}).get("20D", {})

    features = {
        "ret_20d_pct": float(tech.get("ret_20d_pct", 0.0) or 0.0),
        "roe_pct": float(fund.get("roe_pct", 15.0) or 15.0),
        "ttm_pe": float(fund.get("ttm_pe", 25.0) or 25.0),
        "debt_to_equity": float(fund.get("debt_to_equity", 0.5) or 0.5),
        "ml_20d_bps": float(fc_20.get("expected_excess_bps", 0.0) or 0.0),
        "price_above_sma200": 1.0 if tech.get("price_above_sma200") else 0.0,
    }
    features_json = json.dumps(features)
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with target_db.get_connection() as conn:
            # Check for existing trace with same intent, abstracted_prompt, and teacher_model
            cur = conn.execute(
                """
                SELECT id, length(teacher_response) as len_resp FROM copilot_distillation_corpus
                WHERE intent = ? AND abstracted_prompt = ? AND teacher_model = ?
                """,
                (intent, abstracted_prompt, teacher_model),
            )
            existing = cur.fetchone()
            if existing:
                if len(teacher_response) > (existing["len_resp"] or 0):
                    conn.execute(
                        """
                        UPDATE copilot_distillation_corpus
                        SET teacher_response = ?, abstracted_template = ?,
                            telemetry_features_json = ?, tokens_total = ?, created_at = ?
                        WHERE id = ?
                        """,
                        (teacher_response, abstracted_template, features_json, tokens_total, created_at, existing["id"]),
                    )
                    conn.commit()
                return True

            conn.execute(
                """
                INSERT INTO copilot_distillation_corpus (
                    created_at, intent, symbol, sector, user_prompt,
                    abstracted_prompt, telemetry_features_json, teacher_model,
                    teacher_response, abstracted_template, tokens_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    intent,
                    symbol,
                    sector or grounded_data.get("sector", "Equities"),
                    user_prompt,
                    abstracted_prompt,
                    features_json,
                    teacher_model,
                    teacher_response,
                    abstracted_template,
                    tokens_total,
                ),
            )

            # Cap corpus at 2,000 rows
            conn.execute(
                """
                DELETE FROM copilot_distillation_corpus
                WHERE id NOT IN (
                    SELECT id FROM copilot_distillation_corpus ORDER BY id DESC LIMIT 2000
                )
                """
            )
            conn.commit()
            logger.info(f"[DISTILLER] Saved teacher trace for intent '{intent}' ({teacher_model}).")
            return True
    except Exception as e:
        logger.debug(f"[DISTILLER] Failed to persist teacher trace: {e}")
        return False


class CopilotKnowledgeDistiller:
    """
    Manages vectorization, local template indexing, and runtime slot hydration.
    """

    def __init__(
        self,
        db: DatabaseManager,
        model_path: str = DEFAULT_MODEL_PATH,
        meta_path: str = DEFAULT_META_PATH,
    ):
        self.db = db
        self.model_path = model_path
        self.meta_path = meta_path
        self._cached_artifact: Optional[Dict[str, Any]] = None

    def train(self) -> Dict[str, Any]:
        """
        Fits TF-IDF vectorizer over abstracted prompts and Ridge regressor over telemetry features.
        Saves copilot_distilled.joblib (< 2 MB) and metadata JSON.
        """
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, intent, abstracted_prompt, abstracted_template,
                       telemetry_features_json, tokens_total
                FROM copilot_distillation_corpus
                ORDER BY id DESC LIMIT 2000
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            logger.info("[DISTILLER] Corpus is empty; no distillation model trained.")
            return {"trace_count": 0, "status": "empty_corpus"}

        prompts = [r["abstracted_prompt"] for r in rows]
        templates = [r["abstracted_template"] for r in rows]

        # 1. TF-IDF over abstracted prompts
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=2500, min_df=1)
        tfidf_matrix = vectorizer.fit_transform(prompts)

        # 2. Calibrate Ridge regression on quantitative telemetry
        X_feats = []
        y_conviction = []
        for r in rows:
            try:
                feats = json.loads(r.get("telemetry_features_json") or "{}")
                vec = [
                    feats.get("ret_20d_pct", 0.0),
                    feats.get("roe_pct", 15.0),
                    feats.get("ttm_pe", 25.0),
                    feats.get("debt_to_equity", 0.5),
                    feats.get("ml_20d_bps", 0.0),
                    feats.get("price_above_sma200", 0.0),
                ]
                X_feats.append(vec)
                # Proxy target conviction from positive drift & ROE
                target_score = 50.0 + min(35.0, max(-35.0, vec[0] * 1.5 + (vec[1] - 15.0) * 0.8))
                y_conviction.append(target_score)
            except Exception:
                X_feats.append([0.0, 15.0, 25.0, 0.5, 0.0, 0.0])
                y_conviction.append(65.0)

        ridge = Ridge(alpha=1.0)
        ridge.fit(np.array(X_feats), np.array(y_conviction))

        os.makedirs(os.path.dirname(os.path.abspath(self.model_path)), exist_ok=True)
        artifact = {
            "vectorizer": vectorizer,
            "tfidf_matrix": tfidf_matrix,
            "templates": templates,
            "rows": rows,
            "ridge": ridge,
        }
        joblib.dump(artifact, self.model_path, compress=3)
        self._cached_artifact = artifact

        now_iso = datetime.now(timezone.utc).isoformat()
        meta = {
            "trained": True,
            "trained_at": now_iso,
            "trace_count": len(rows),
            "corpus_size": len(rows),
            "vocabulary_size": len(vectorizer.vocabulary_),
            "model_path": self.model_path,
        }
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info(
            f"[DISTILLER] Successfully trained distillation engine with {len(rows)} traces (vocab={len(vectorizer.vocabulary_)})."
        )
        return meta

    def _load_artifact(self) -> Optional[Dict[str, Any]]:
        if self._cached_artifact is not None:
            return self._cached_artifact
        if os.path.exists(self.model_path):
            try:
                self._cached_artifact = joblib.load(self.model_path)
                return self._cached_artifact
            except Exception as e:
                logger.warning(f"[DISTILLER] Failed to load {self.model_path}: {e}")
        return None

    def retrieve_and_hydrate(
        self,
        prompt: str,
        intent: str = "DIRECT_QA",
        symbol: str = "NIFTY 50",
        grounded_data: Optional[Dict[str, Any]] = None,
        min_similarity: float = 0.35,
        stock_telemetry: Optional[Dict[str, Any]] = None,
        return_score: bool = False,
    ) -> Any:
        """
        Matches user prompt against distilled corpus using cosine similarity on TF-IDF.
        If similarity >= min_similarity, hydrates canonical placeholders with live grounded data.
        """
        artifact = self._load_artifact()
        if not artifact:
            return None

        data = grounded_data or stock_telemetry or {}
        vectorizer: TfidfVectorizer = artifact["vectorizer"]
        tfidf_matrix = artifact["tfidf_matrix"]
        templates: List[str] = artifact["templates"]
        rows: List[Dict[str, Any]] = artifact["rows"]

        abstracted = abstract_prompt_text(prompt, symbol, data.get("company_name"))
        q_vec = vectorizer.transform([abstracted])
        sims = cosine_similarity(q_vec, tfidf_matrix).flatten()

        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score < min_similarity:
            return None

        # Prefer matching intent when possible
        candidate_template = templates[best_idx]
        for idx in np.argsort(-sims)[:5]:
            if rows[idx].get("intent") == intent and sims[idx] >= min_similarity:
                candidate_template = templates[idx]
                best_score = float(sims[idx])
                break

        # Hydrate all slots with live target data
        hydrated = self._hydrate_template(candidate_template, symbol, data)
        return (hydrated, best_score) if return_score else hydrated

    def _hydrate_template(self, template: str, symbol: str, data: Dict[str, Any]) -> str:
        """Fills canonical {{...}} slots with live values from grounded target data."""
        price = data.get("current_price") or data.get("latest_close") or 0.0
        comp_name = data.get("company_name") or symbol
        tech = data.get("technicals", {})
        fund = data.get("fundamentals", {})
        draw = data.get("historical_drawdowns", {})
        ml = data.get("ml_forecast", {})
        fc_20 = ml.get("forecasts", {}).get("20D", {})

        sma200 = tech.get("sma_200")
        ret20d = tech.get("ret_20d_pct", 0.0) or 0.0
        roe = fund.get("roe_pct")
        pe = fund.get("ttm_pe")
        ml_ret = fc_20.get("expected_return_pct", 0.0) or 0.0
        ml_bps = fc_20.get("expected_excess_bps", 0.0) or 0.0

        h52 = draw.get("high_52w", {}).get("price", 0.0) or 0.0
        l52 = draw.get("low_52w", {}).get("price", 0.0) or 0.0
        target = data.get("target_price") or round(price * 1.05, 2)
        floor = data.get("stop_loss") or round(price * 0.95, 2)

        replacements = {
            "{{SYMBOL}}": symbol,
            "{{COMPANY_NAME}}": comp_name,
            "{{PRICE}}": f"₹{price:.2f}",
            "{{SMA200}}": f"₹{sma200:.2f}" if sma200 else "N/A",
            "{{RET20D}}": f"{ret20d:+.2f}%",
            "{{ROE}}": f"{roe:.1f}%" if roe is not None else "—",
            "{{PE}}": f"{pe:.1f}x" if pe is not None else "—",
            "{{ML_20D_RET}}": f"{ml_ret:+.2f}%",
            "{{ML_20D_BPS}}": f"{ml_bps:+.1f}",
            "{{TARGET_20D}}": f"₹{target:.2f}",
            "{{FLOOR_20D}}": f"₹{floor:.2f}",
            "{{HIGH_52W}}": f"₹{h52:.2f}",
            "{{LOW_52W}}": f"₹{l52:.2f}",
        }

        out = template
        for slot, val in replacements.items():
            out = out.replace(slot, str(val))
        return out

    def get_distillation_stats(self) -> Dict[str, Any]:
        """Returns distillation metrics for the Engine & Quota UI drawer."""
        trace_count = 0
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM copilot_distillation_corpus")
                row = cur.fetchone()
                if row:
                    trace_count = row[0]
        except Exception:
            pass

        meta = {}
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass

        # Auto-seed initial corpus and train distillation artifacts if fewer than 10 traces exist
        if trace_count < 10 or not meta.get("trained"):
            try:
                self.seed_from_existing_telemetry()
                return self.get_distillation_stats()
            except Exception as se:
                logger.warning(f"[DISTILLER] Auto-seeding distillation corpus failed: {se}")

        return {
            "trace_count": trace_count,
            "last_trained_at": meta.get("trained_at"),
            "vocabulary_size": meta.get("vocabulary_size", 0),
            "model_path": self.model_path,
        }

    def seed_from_existing_telemetry(self) -> Dict[str, Any]:
        """
        Bootstraps initial parameterized templates from canonical seed templates
        and existing market_catalysts or equity_news_feed if copilot_distillation_corpus
        has < 10 traces, and trains the TF-IDF + Ridge artifacts immediately.
        """
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT COUNT(*) FROM copilot_distillation_corpus")
                row = cur.fetchone()
                existing_count = row[0] if row else 0
        except Exception:
            existing_count = 0

        if existing_count >= 10:
            return {"status": "already_seeded", "trace_count": existing_count}

        seed_traces = [
            {
                "intent": "DIRECT_QA",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "Direct Alpha Brief for {{SYMBOL}}",
                "abstracted_prompt": "Direct Alpha Brief for {{SYMBOL}}",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **Alpha & Structural Momentum Brief: {{SYMBOL}} ({{COMPANY_NAME}})**\n\n"
                    "**Current Market Stance:**\n"
                    "- **Price Action:** Trading at {{PRICE}} (20D Momentum: {{RET20D}}), positioned relative to the 200-day moving average at {{SMA200}}.\n"
                    "- **ML Multi-Horizon Projection:** The 20D quantitative forecast anticipates {{ML_20D_RET}} (Excess Alpha: {{ML_20D_BPS}} bps).\n"
                    "- **Fundamental Quality:** ROE stands at {{ROE}}, trailing P/E is {{PE}}.\n\n"
                    "**Tactical Range & Invalidation:**\n"
                    "- **Upside Objective (20D):** {{TARGET_20D}}\n"
                    "- **Downside Invalidation Floor:** {{FLOOR_20D}}\n"
                    "- **52-Week Range:** Low {{LOW_52W}} — High {{HIGH_52W}}\n\n"
                    "**Quantitative Conviction:** Balanced systematic alpha with favorable risk-reward asymmetry."
                ),
                "abstracted_template": (
                    "### **Alpha & Structural Momentum Brief: {{SYMBOL}} ({{COMPANY_NAME}})**\n\n"
                    "**Current Market Stance:**\n"
                    "- **Price Action:** Trading at {{PRICE}} (20D Momentum: {{RET20D}}), positioned relative to the 200-day moving average at {{SMA200}}.\n"
                    "- **ML Multi-Horizon Projection:** The 20D quantitative forecast anticipates {{ML_20D_RET}} (Excess Alpha: {{ML_20D_BPS}} bps).\n"
                    "- **Fundamental Quality:** ROE stands at {{ROE}}, trailing P/E is {{PE}}.\n\n"
                    "**Tactical Range & Invalidation:**\n"
                    "- **Upside Objective (20D):** {{TARGET_20D}}\n"
                    "- **Downside Invalidation Floor:** {{FLOOR_20D}}\n"
                    "- **52-Week Range:** Low {{LOW_52W}} — High {{HIGH_52W}}\n\n"
                    "**Quantitative Conviction:** Balanced systematic alpha with favorable risk-reward asymmetry."
                ),
                "telemetry": {"ret_20d_pct": 2.5, "roe_pct": 18.0, "ttm_pe": 22.0, "debt_to_equity": 0.4, "ml_20d_bps": 85.0, "price_above_sma200": 1.0},
                "tokens": 420
            },
            {
                "intent": "DEBATE_THESIS",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "Debate Bull vs Bear Thesis for {{SYMBOL}}",
                "abstracted_prompt": "Debate Bull vs Bear Thesis for {{SYMBOL}}",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **Committee Deliberation & Conviction Stance: {{SYMBOL}}**\n\n"
                    "**1. Bull Thesis (Alpha & Capital Efficiency):**\n"
                    "- Resilient capital allocation with verified ROE at {{ROE}}.\n"
                    "- Walk-forward ML engine models an expected 20D drift of {{ML_20D_RET}}.\n"
                    "- Tactical upside target sits at {{TARGET_20D}} supported by institutional accumulation.\n\n"
                    "**2. Bear Thesis (Risk Vectors & Vulnerabilities):**\n"
                    "- Trailing P/E multiple of {{PE}} leaves limited margin of safety for quarterly earnings misses.\n"
                    "- Structural invalidation floor is pegged at {{FLOOR_20D}}; a decisive breach exposes deeper retracement.\n"
                    "- Sector rotation and macro liquidity could compress near-term multiples.\n\n"
                    "**3. PM Verdict & Execution Stance:**\n"
                    "- Constructive allocation stance above {{SMA200}} with disciplined stop protection at {{FLOOR_20D}}."
                ),
                "abstracted_template": (
                    "### **Committee Deliberation & Conviction Stance: {{SYMBOL}}**\n\n"
                    "**1. Bull Thesis (Alpha & Capital Efficiency):**\n"
                    "- Resilient capital allocation with verified ROE at {{ROE}}.\n"
                    "- Walk-forward ML engine models an expected 20D drift of {{ML_20D_RET}}.\n"
                    "- Tactical upside target sits at {{TARGET_20D}} supported by institutional accumulation.\n\n"
                    "**2. Bear Thesis (Risk Vectors & Vulnerabilities):**\n"
                    "- Trailing P/E multiple of {{PE}} leaves limited margin of safety for quarterly earnings misses.\n"
                    "- Structural invalidation floor is pegged at {{FLOOR_20D}}; a decisive breach exposes deeper retracement.\n"
                    "- Sector rotation and macro liquidity could compress near-term multiples.\n\n"
                    "**3. PM Verdict & Execution Stance:**\n"
                    "- Constructive allocation stance above {{SMA200}} with disciplined stop protection at {{FLOOR_20D}}."
                ),
                "telemetry": {"ret_20d_pct": 1.2, "roe_pct": 16.5, "ttm_pe": 26.0, "debt_to_equity": 0.6, "ml_20d_bps": 40.0, "price_above_sma200": 1.0},
                "tokens": 480
            },
            {
                "intent": "COMPARE_PEER",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "Compare {{SYMBOL}} vs sector peer",
                "abstracted_prompt": "Compare {{SYMBOL}} vs sector peer",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **Comparative Factor Positioning: {{SYMBOL}}**\n\n"
                    "- **Valuation & Quality:** {{SYMBOL}} trades at {{PRICE}} with a P/E of {{PE}} and ROE of {{ROE}}, exhibiting robust quality rank.\n"
                    "- **Momentum Profile:** 20D return of {{RET20D}} relative to the 200-day simple moving average at {{SMA200}}.\n"
                    "- **Machine Learning Projection:** Multi-horizon walk-forward ML models {{ML_20D_RET}} return potential.\n"
                    "- **Risk Boundary:** Key invalidation floor at {{FLOOR_20D}} against target resistance at {{TARGET_20D}}."
                ),
                "abstracted_template": (
                    "### **Comparative Factor Positioning: {{SYMBOL}}**\n\n"
                    "- **Valuation & Quality:** {{SYMBOL}} trades at {{PRICE}} with a P/E of {{PE}} and ROE of {{ROE}}, exhibiting robust quality rank.\n"
                    "- **Momentum Profile:** 20D return of {{RET20D}} relative to the 200-day simple moving average at {{SMA200}}.\n"
                    "- **Machine Learning Projection:** Multi-horizon walk-forward ML models {{ML_20D_RET}} return potential.\n"
                    "- **Risk Boundary:** Key invalidation floor at {{FLOOR_20D}} against target resistance at {{TARGET_20D}}."
                ),
                "telemetry": {"ret_20d_pct": 3.1, "roe_pct": 21.0, "ttm_pe": 19.5, "debt_to_equity": 0.3, "ml_20d_bps": 110.0, "price_above_sma200": 1.0},
                "tokens": 390
            },
            {
                "intent": "WATCHLIST_AUDIT",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "Review my watchlist",
                "abstracted_prompt": "Review my watchlist",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **Systematic Watchlist & Portfolio Audit**\n\n"
                    "- **Momentum & Trend Leaders:** Focus capital on symbols sustaining positive 20D excess alpha above sector benchmarks.\n"
                    "- **Quality Filter:** Favor holdings with verified ROE > 15% and conservative debt-to-equity (< 0.8).\n"
                    "- **Risk Management:** Maintain strict discipline on equities violating their 200 SMA baseline."
                ),
                "abstracted_template": (
                    "### **Systematic Watchlist & Portfolio Audit**\n\n"
                    "- **Momentum & Trend Leaders:** Focus capital on symbols sustaining positive 20D excess alpha above sector benchmarks.\n"
                    "- **Quality Filter:** Favor holdings with verified ROE > 15% and conservative debt-to-equity (< 0.8).\n"
                    "- **Risk Management:** Maintain strict discipline on equities violating their 200 SMA baseline."
                ),
                "telemetry": {"ret_20d_pct": 0.5, "roe_pct": 17.0, "ttm_pe": 24.0, "debt_to_equity": 0.5, "ml_20d_bps": 30.0, "price_above_sma200": 1.0},
                "tokens": 350
            },
            {
                "intent": "DIRECT_QA",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "What was {{SYMBOL}}'s last major dip?",
                "abstracted_prompt": "What was {{SYMBOL}}'s last major dip?",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **Historical Drawdown & Volatility Analysis: {{SYMBOL}}**\n\n"
                    "- **52-Week Range:** {{SYMBOL}} has traded between a 52-week low of {{LOW_52W}} and a high of {{HIGH_52W}}.\n"
                    "- **Current Positioning:** At {{PRICE}}, the stock trades relative to its 200 SMA at {{SMA200}} with 20D return of {{RET20D}}.\n"
                    "- **Support Invalidation Floor:** Key tactical support is established at {{FLOOR_20D}}.\n"
                    "- **Target Rebound Potential:** Systematic model projects {{ML_20D_RET}} over the next 20 sessions toward {{TARGET_20D}}."
                ),
                "abstracted_template": (
                    "### **Historical Drawdown & Volatility Analysis: {{SYMBOL}}**\n\n"
                    "- **52-Week Range:** {{SYMBOL}} has traded between a 52-week low of {{LOW_52W}} and a high of {{HIGH_52W}}.\n"
                    "- **Current Positioning:** At {{PRICE}}, the stock trades relative to its 200 SMA at {{SMA200}} with 20D return of {{RET20D}}.\n"
                    "- **Support Invalidation Floor:** Key tactical support is established at {{FLOOR_20D}}.\n"
                    "- **Target Rebound Potential:** Systematic model projects {{ML_20D_RET}} over the next 20 sessions toward {{TARGET_20D}}."
                ),
                "telemetry": {"ret_20d_pct": -1.5, "roe_pct": 15.0, "ttm_pe": 25.0, "debt_to_equity": 0.5, "ml_20d_bps": 50.0, "price_above_sma200": 1.0},
                "tokens": 410
            },
            {
                "intent": "DIRECT_QA",
                "symbol": "SYSTEM",
                "sector": "Broad Market",
                "user_prompt": "Summarize {{SYMBOL}}'s 20D risk/reward",
                "abstracted_prompt": "Summarize {{SYMBOL}}'s 20D risk/reward",
                "teacher_model": "distilled/seed-v1",
                "teacher_response": (
                    "### **20D Quantitative Risk/Reward Profile: {{SYMBOL}}**\n\n"
                    "- **Expected Return:** Walk-forward ML engine projects {{ML_20D_RET}} ({{ML_20D_BPS}} bps excess return).\n"
                    "- **Asymmetry Metrics:** Upside target at {{TARGET_20D}} versus downside invalidation floor at {{FLOOR_20D}}.\n"
                    "- **Fundamental Anchor:** Verified ROE of {{ROE}} and P/E of {{PE}} support structural quality.\n"
                    "- **Trend Health:** Price {{PRICE}} vs 200 SMA {{SMA200}}."
                ),
                "abstracted_template": (
                    "### **20D Quantitative Risk/Reward Profile: {{SYMBOL}}**\n\n"
                    "- **Expected Return:** Walk-forward ML engine projects {{ML_20D_RET}} ({{ML_20D_BPS}} bps excess return).\n"
                    "- **Asymmetry Metrics:** Upside target at {{TARGET_20D}} versus downside invalidation floor at {{FLOOR_20D}}.\n"
                    "- **Fundamental Anchor:** Verified ROE of {{ROE}} and P/E of {{PE}} support structural quality.\n"
                    "- **Trend Health:** Price {{PRICE}} vs 200 SMA {{SMA200}}."
                ),
                "telemetry": {"ret_20d_pct": 1.8, "roe_pct": 19.0, "ttm_pe": 23.0, "debt_to_equity": 0.4, "ml_20d_bps": 75.0, "price_above_sma200": 1.0},
                "tokens": 380
            }
        ]

        # Ingest from existing market_catalysts if available
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_catalysts'")
                if cur.fetchone():
                    cats = conn.execute(
                        "SELECT symbol, sector, causal_headline, causal_bullets, move_pct, rvol FROM market_catalysts ORDER BY id DESC LIMIT 5"
                    ).fetchall()
                    for cat in cats:
                        sym = cat["symbol"]
                        head = cat["causal_headline"]
                        bullets = json.loads(cat["causal_bullets"] or "[]")
                        b_text = "\n".join([f"- {b}" for b in bullets[:3]])
                        seed_traces.append({
                            "intent": "CATALYST_RADAR",
                            "symbol": sym,
                            "sector": cat["sector"] or "Equities",
                            "user_prompt": f"Why is {sym} moving today?",
                            "abstracted_prompt": "Why is {{SYMBOL}} moving today?",
                            "teacher_model": "distilled/seed-v1",
                            "teacher_response": f"### **Causal Anomaly Attribution: {sym}**\n\n**Headline:** {head}\n\n**Attribution Drivers:**\n{b_text}\n\n**Systematic Horizon:** Monitor support at {{{{FLOOR_20D}}}} and target at {{{{TARGET_20D}}}}.",
                            "abstracted_template": f"### **Causal Anomaly Attribution: {{{{SYMBOL}}}}**\n\n**Headline:** {head}\n\n**Attribution Drivers:**\n{b_text}\n\n**Systematic Horizon:** Monitor support at {{{{FLOOR_20D}}}} and target at {{{{TARGET_20D}}}}.",
                            "telemetry": {"ret_20d_pct": float(cat["move_pct"] or 0.0), "roe_pct": 16.0, "ttm_pe": 22.0, "debt_to_equity": 0.5, "ml_20d_bps": 50.0, "price_above_sma200": 1.0},
                            "tokens": 320
                        })
        except Exception as e:
            logger.debug(f"[DISTILLER] Note: unable to harvest from market_catalysts: {e}")

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            with self.db.get_connection() as conn:
                for t in seed_traces:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO copilot_distillation_corpus (
                            created_at, intent, symbol, sector, user_prompt,
                            abstracted_prompt, telemetry_features_json, teacher_model,
                            teacher_response, abstracted_template, tokens_total
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now_iso,
                            t["intent"],
                            t["symbol"],
                            t["sector"],
                            t["user_prompt"],
                            t["abstracted_prompt"],
                            json.dumps(t["telemetry"]),
                            t["teacher_model"],
                            t["teacher_response"],
                            t["abstracted_template"],
                            t["tokens"],
                        )
                    )
                conn.commit()
            logger.info(f"[DISTILLER] Bootstrapped {len(seed_traces)} seed traces into copilot_distillation_corpus.")
        except Exception as e:
            logger.warning(f"[DISTILLER] Failed to persist seed traces: {e}")

        # Train model immediately with the bootstrapped seeds
        train_res = self.train()
        return {"status": "seeded", "traces_seeded": len(seed_traces), "train_results": train_res}
