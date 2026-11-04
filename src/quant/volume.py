import math
from typing import List, Optional, Tuple, Dict, Any

def adjust_volume_for_corporate_actions(
    records: List[Dict[str, Any]],
    corporate_actions: Optional[List[Dict[str, Any]]] = None
) -> List[int]:
    """
    Adjusts historical trading volumes for share-count changes (splits, bonuses).
    Formula: Vol_adj,t = Vol_t / product_{ex_date > t} (adjustment_factor)
    If a 1:1 bonus issue occurs (factor 0.5, doubling shares), 1 share traded before
    the bonus corresponds to 1 / 0.5 = 2 shares in today's share count.
    This prevents artificial volume spikes when post-bonus activity is compared to pre-bonus levels.
    """
    if not records:
        return []

    split_bonus_events = []
    if corporate_actions:
        for ca in corporate_actions:
            atype = ca.get("action_type", "").upper()
            ex_d = ca.get("ex_date", "")
            factor = float(ca.get("adjustment_factor", 1.0))
            if any(term in atype for term in ["SPLIT", "BONUS", "CONSOLIDATION"]) and factor > 0:
                split_bonus_events.append((ex_d, factor))

    adjusted_volumes: List[int] = []
    for r in records:
        d = r["trading_date"]
        raw_vol = int(r.get("volume", 0))

        cum_factor = 1.0
        for ex_d, factor in split_bonus_events:
            if ex_d > d:
                cum_factor *= factor

        if cum_factor > 0:
            adj_vol = int(round(raw_vol / cum_factor))
        else:
            adj_vol = raw_vol

        adjusted_volumes.append(adj_vol)

    return adjusted_volumes

def calculate_volume_ratio(
    volume_history: List[int],
    window: int = 20
) -> Optional[float]:
    """
    Computes today's Volume Ratio relative to trailing N sessions:
    VR_t = V_t / ADV_{t-1, N}
    Returns None if fewer than `window + 1` observations are provided (warm-up period).
    """
    if len(volume_history) < (window + 1):
        return None

    today_vol = volume_history[-1]
    baseline_vols = volume_history[-(window + 1):-1]
    adv = sum(baseline_vols) / float(window)

    if adv <= 0:
        return 0.0

    return today_vol / adv

def calculate_volume_zscores(
    volume_history: List[int],
    window: int = 50
) -> Tuple[Optional[float], Optional[float]]:
    """
    Computes Volume Z-Score and Log-Normal Volume Z-Score relative to trailing M sessions:
    Z_V = (V_t - mu) / sigma
    Z_lnV = (ln(V_t) - mu_ln) / sigma_ln

    Returns (None, None) if fewer than `window + 1` observations are provided (warm-up period).
    Handles zero-variance windows by returning (0.0, 0.0) without ZeroDivisionError.
    """
    if len(volume_history) < (window + 1):
        return None, None

    today_vol = volume_history[-1]
    baseline_vols = volume_history[-(window + 1):-1]

    # 1. Raw Volume Z-Score
    mu = sum(baseline_vols) / float(window)
    var = sum((v - mu) ** 2 for v in baseline_vols) / float(window - 1)
    sigma = math.sqrt(var)

    raw_z = (today_vol - mu) / sigma if sigma > 0 else 0.0

    # 2. Log-Normal Volume Z-Score (handles heavy right skew in trading volumes)
    log_vols = [math.log(max(v, 1)) for v in baseline_vols]
    today_log_vol = math.log(max(today_vol, 1))

    mu_log = sum(log_vols) / float(window)
    var_log = sum((lv - mu_log) ** 2 for lv in log_vols) / float(window - 1)
    sigma_log = math.sqrt(var_log)

    log_z = (today_log_vol - mu_log) / sigma_log if sigma_log > 0 else 0.0

    return raw_z, log_z

def evaluate_volume_anomalies(
    volume_history: List[int],
    vr_threshold: float = 2.5,
    z_threshold: float = 2.5
) -> Dict[str, Any]:
    """
    Evaluates both Volume Ratio and Volume Z-Score independently.
    Demonstrates that an anomaly can trigger on ratio without triggering on Z-score, and vice versa.
    """
    vr = calculate_volume_ratio(volume_history, window=20)
    raw_z, log_z = calculate_volume_zscores(volume_history, window=50)

    is_spike_ratio = (vr is not None and vr >= vr_threshold)
    is_spike_zscore = (raw_z is not None and raw_z >= z_threshold)

    return {
        "volume_ratio_20d": vr,
        "volume_zscore_50d": raw_z,
        "volume_log_zscore_50d": log_z,
        "is_volume_spike_ratio": int(is_spike_ratio),
        "is_volume_spike_zscore": int(is_spike_zscore),
        "is_warmup_period": (vr is None or raw_z is None)
    }
