"""
src/quant/validation.py
Combinatorial Purged Cross-Validation (CPCV) & Bailey-López de Prado Deflated Sharpe Ratio (DSR).
Phase 3 Deliverable — Eliminates backtest overfitting, selection bias, and temporal leakage.

Mathematical Invariants:
1. CPCV(n_splits=6, n_test_splits=2):
   - Generates binom(6, 2) = 15 combinations and reconstructs 5 complete OOS backtest paths.
   - Purge window strictly equals label horizon H (purge_days = H).
   - Embargo window defaults to max(H, 5) sessions immediately following test folds.
2. Deflated Sharpe Ratio (DSR):
   - Bailey & López de Prado (2014) formulation using excess kurtosis (Normal = 0):
     V[SR_hat] = (1 / (T - 1)) * (1 - gamma_3 * SR_hat + ((gamma_4_ex + 2) / 4) * SR_hat^2)
   - When gamma_3 = 0 and gamma_4_ex = 0: V[SR_hat] = (1 + 0.5 * SR_hat^2) / (T - 1).
   - Penalizes multiple testing trials M via extreme value distribution threshold SR*.
"""

import math
import itertools
import logging
from typing import Dict, Any, List, Tuple, Optional, Generator, Union
import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger("MIL.Validation")

EULER_MASCHERONI = 0.5772156649015328606065120900824


class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation (CPCV) for path-dependent financial time-series.
    Generates all combinations of test folds with rigorous label-horizon purging and embargoing.
    """

    def __init__(
        self,
        n_splits: int = 6,
        n_test_splits: int = 2,
        horizon_days: int = 20,
        embargo_days: Optional[int] = None
    ):
        if n_splits < 3:
            raise ValueError(f"n_splits must be >= 3, got {n_splits}")
        if n_test_splits < 1 or n_test_splits >= n_splits:
            raise ValueError(f"n_test_splits must be in [1, n_splits-1], got {n_test_splits}")

        self.n_splits = int(n_splits)
        self.n_test_splits = int(n_test_splits)
        self.horizon_days = int(horizon_days)
        self.embargo_days = int(embargo_days) if embargo_days is not None else max(self.horizon_days, 5)

        # Total combinations = binom(N, k)
        self.total_combinations = math.comb(self.n_splits, self.n_test_splits)
        # Number of complete OOS paths = (k / N) * binom(N, k)
        self.n_oos_paths = int((self.n_test_splits / self.n_splits) * self.total_combinations)

    def split(
        self,
        X: Union[np.ndarray, pd.DataFrame, List[Any]],
        y: Optional[Union[np.ndarray, pd.Series]] = None,
        groups: Optional[Union[np.ndarray, pd.Series]] = None
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yields (train_indices, test_indices) for each of the binom(N, k) combinations.
        Applies label-horizon purging before test blocks and embargoing after test blocks.
        """
        n_samples = len(X)
        if n_samples < self.n_splits * (self.horizon_days + 5):
            raise ValueError(f"Sample size ({n_samples}) is too small for {self.n_splits} purged splits.")

        # Date-based purging/embargoing when DataFrame has trading_date or explicit groups are provided
        date_labels = None
        if groups is not None and len(groups) == n_samples:
            date_labels = np.asarray(groups).astype(str)
        elif isinstance(X, pd.DataFrame) and "trading_date" in X.columns:
            date_labels = X["trading_date"].astype(str).to_numpy()

        if date_labels is not None:
            unique_dates = np.array(sorted(set(date_labels)))
            n_dates = len(unique_dates)
            if n_dates >= self.n_splits * 2:
                date_to_pos = {d: idx for idx, d in enumerate(unique_dates)}
                row_date_pos = np.array([date_to_pos[d] for d in date_labels], dtype=int)
                date_bounds = np.linspace(0, n_dates, self.n_splits + 1, dtype=int)
                date_blocks = [np.arange(date_bounds[i], date_bounds[i + 1]) for i in range(self.n_splits)]

                for test_group_ids in itertools.combinations(range(self.n_splits), self.n_test_splits):
                    test_group_set = set(test_group_ids)
                    test_date_mask = np.zeros(n_dates, dtype=bool)
                    for gid in test_group_ids:
                        test_date_mask[date_blocks[gid]] = True

                    drop_date_mask = test_date_mask.copy()
                    for gid in test_group_ids:
                        t_start = int(date_bounds[gid])
                        t_end = int(date_bounds[gid + 1])
                        p_start = max(0, t_start - self.horizon_days)
                        e_end = min(n_dates, t_end + self.embargo_days)
                        drop_date_mask[p_start:t_start] = True
                        drop_date_mask[t_end:e_end] = True

                    test_indices = np.where(test_date_mask[row_date_pos])[0]
                    train_indices = np.where(~drop_date_mask[row_date_pos])[0]
                    assert len(np.intersect1d(train_indices, test_indices)) == 0, "Purging invariant failure: Overlapping train/test indices!"
                    yield train_indices, test_indices
                return

        indices = np.arange(n_samples)

        # Divide into N contiguous chronological blocks
        block_bounds = np.linspace(0, n_samples, self.n_splits + 1, dtype=int)
        blocks = [indices[block_bounds[i]: block_bounds[i + 1]] for i in range(self.n_splits)]

        # Generate all binom(N, k) test group combinations
        for test_group_ids in itertools.combinations(range(self.n_splits), self.n_test_splits):
            test_group_set = set(test_group_ids)
            train_group_ids = [i for i in range(self.n_splits) if i not in test_group_set]

            # Build raw test indices
            test_idx_list = []
            for gid in test_group_ids:
                test_idx_list.extend(blocks[gid])
            test_indices = np.array(sorted(test_idx_list))

            # Build candidate train indices
            train_idx_list = []
            for gid in train_group_ids:
                train_idx_list.extend(blocks[gid])
            raw_train = np.array(sorted(train_idx_list))

            # Purge & Embargo masks
            # For each test block [start_t, end_t):
            # 1. Purge: Train observations whose forward label overlaps into test: [start_t - H, start_t)
            # 2. Embargo: Train observations immediately following test block: [end_t, end_t + embargo)
            drop_mask = np.zeros(len(raw_train), dtype=bool)

            for gid in test_group_ids:
                test_start = block_bounds[gid]
                test_end = block_bounds[gid + 1]

                purge_start = max(0, test_start - self.horizon_days)
                embargo_end = min(n_samples, test_end + self.embargo_days)

                # Purge window: [purge_start, test_start)
                purge_cond = (raw_train >= purge_start) & (raw_train < test_start)
                # Embargo window: [test_end, embargo_end)
                embargo_cond = (raw_train >= test_end) & (raw_train < embargo_end)

                drop_mask |= purge_cond | embargo_cond

            train_indices = raw_train[~drop_mask]

            # Strict Invariant: Zero intersection
            assert len(np.intersect1d(train_indices, test_indices)) == 0, "Purging invariant failure: Overlapping train/test indices!"

            yield train_indices, test_indices

    @staticmethod
    def split_train_holdout(
        df: pd.DataFrame,
        holdout_sessions: int = 252
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Reserves an untouched chronological final holdout slice completely excluded
        from CPCV hyperparameter tuning and model promotion decisions.
        """
        if df.empty or len(df) <= holdout_sessions:
            raise ValueError(f"Insufficient samples ({len(df)}) for holdout window ({holdout_sessions}).")

        if "trading_date" in df.columns:
            unique_dates = sorted(df["trading_date"].astype(str).unique())
            if len(unique_dates) > holdout_sessions + 10:
                cutoff_date = unique_dates[-holdout_sessions]
                dev_df = df[df["trading_date"].astype(str) < cutoff_date].copy().reset_index(drop=True)
                holdout_df = df[df["trading_date"].astype(str) >= cutoff_date].copy().reset_index(drop=True)
                if not dev_df.empty and not holdout_df.empty:
                    return dev_df, holdout_df

        dev_df = df.iloc[:-holdout_sessions].copy().reset_index(drop=True)
        holdout_df = df.iloc[-holdout_sessions:].copy().reset_index(drop=True)
        return dev_df, holdout_df


def deflated_sharpe_ratio(
    returns: Optional[Union[np.ndarray, pd.Series, List[float]]] = None,
    sharpe_hat: Optional[float] = None,
    skewness: Optional[float] = None,
    excess_kurtosis: Optional[float] = None,
    t_samples: Optional[int] = None,
    n_trials: int = 1,
    sharpe_benchmark: float = 0.0,
    annualized_factor: float = 1.0
) -> Dict[str, Any]:
    """
    Computes Bailey & López de Prado's Deflated Sharpe Ratio (DSR) using excess kurtosis.

    Mathematical Formulation:
        V[SR_hat] = (1 / (T - 1)) * (1 - gamma_3 * SR_hat + ((gamma_4_ex + 2) / 4) * SR_hat^2)

    When gamma_3 = 0 and gamma_4_ex = 0 (Normal distribution):
        V[SR_hat] = (1 + 0.5 * SR_hat^2) / (T - 1)

    Accounts for:
    - Non-normality (skewness gamma_3, excess kurtosis gamma_4_ex).
    - Sample track record length T.
    - Multiple testing selection bias across M trials.

    Returns:
        dict with keys: 'dsr', 'estimated_sharpe', 'sharpe_star', 'variance_sr',
                        'skewness', 'excess_kurtosis', 'n_trials', 't_samples'.
    """
    m_trials = max(1, int(n_trials))

    # 1. Derive statistical moments from returns or explicit inputs
    if returns is not None:
        r = np.asarray(returns, dtype=float)
        r = r[~np.isnan(r)]
        if len(r) < 3:
            raise ValueError(f"Need at least 3 valid return observations, got {len(r)}")

        t = len(r)
        mean_r = float(np.mean(r))
        std_r = float(np.std(r, ddof=1))
        if std_r <= 1e-8:
            return {
                "dsr": 0.0,
                "estimated_sharpe": 0.0,
                "sharpe_star": 0.0,
                "variance_sr": 1.0,
                "skewness": 0.0,
                "excess_kurtosis": 0.0,
                "n_trials": m_trials,
                "t_samples": t
            }

        sr = (mean_r / std_r) * math.sqrt(annualized_factor)
        gamma_3 = float(stats.skew(r))
        # scipy.stats.kurtosis with fisher=True computes excess kurtosis (Normal = 0.0)
        gamma_4_ex = float(stats.kurtosis(r, fisher=True))
    else:
        if None in (sharpe_hat, skewness, excess_kurtosis, t_samples):
            raise ValueError("Must provide either returns array or explicit (sharpe_hat, skewness, excess_kurtosis, t_samples).")
        sr = float(sharpe_hat)
        gamma_3 = float(skewness)
        gamma_4_ex = float(excess_kurtosis)
        t = int(t_samples)

    if t <= 2:
        raise ValueError(f"Sample length T must be > 2, got {t}")

    # 2. Analytical Variance of estimated Sharpe Ratio under non-normality
    # V[SR] = (1 / (T - 1)) * (1 - gamma_3 * SR + ((gamma_4_ex + 2) / 4) * SR^2)
    # Note: If SR is annualized, variance scales by 1/T_sessions
    sr_unann = sr / math.sqrt(annualized_factor) if annualized_factor > 0 else sr
    var_sr_unann = (1.0 / (t - 1)) * (1.0 - gamma_3 * sr_unann + ((gamma_4_ex + 2.0) / 4.0) * (sr_unann ** 2))
    var_sr = max(1e-9, var_sr_unann * annualized_factor)
    std_sr = math.sqrt(var_sr)

    # 3. Expected Maximum Sharpe Ratio across M trials under false discovery
    if m_trials == 1:
        sr_star = float(sharpe_benchmark)
    else:
        # Extreme Value Distribution quantile for maximum of M standard normals:
        # Z_M = (1 - gamma_E) * Phi^{-1}(1 - 1/M) + gamma_E * Phi^{-1}(1 - 1/(M * e))
        q1 = stats.norm.ppf(1.0 - (1.0 / m_trials))
        q2 = stats.norm.ppf(1.0 - (1.0 / (m_trials * math.e)))
        z_m = ((1.0 - EULER_MASCHERONI) * q1) + (EULER_MASCHERONI * q2)
        sr_star = float(sharpe_benchmark) + (std_sr * z_m)

    # 4. Deflated Sharpe Ratio = Phi((SR_hat - SR*) / std_sr)
    z_stat = (sr - sr_star) / std_sr
    dsr = float(stats.norm.cdf(z_stat))

    return {
        "dsr": round(dsr, 6),
        "estimated_sharpe": round(sr, 4),
        "sharpe_star": round(sr_star, 4),
        "variance_sr": round(var_sr, 6),
        "std_sr": round(std_sr, 6),
        "skewness": round(gamma_3, 4),
        "excess_kurtosis": round(gamma_4_ex, 4),
        "n_trials": m_trials,
        "t_samples": t
    }
