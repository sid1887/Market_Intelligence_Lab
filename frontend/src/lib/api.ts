/**
 * Market Intelligence Lab — Unified Zero-Latency API Client
 * Milestone B10.5 — hover-prefetch cache, typed endpoints, ngrok bypass headers
 */

const RAW_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
export const API_BASE = RAW_BASE.endsWith("/api/v1")
  ? RAW_BASE
  : `${RAW_BASE.replace(/\/$/, "")}/api/v1`;

const DEFAULT_HEADERS: HeadersInit = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

// In-memory LRU-style cache for zero-latency stock switching
const memoryCache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL_MS = 60_000; // 60 seconds

export async function apiFetch<T>(endpoint: string, useCache = true): Promise<T> {
  const url = `${API_BASE}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  if (useCache && memoryCache.has(url)) {
    const cached = memoryCache.get(url)!;
    if (Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data as T;
    }
  }

  const res = await fetch(url, {
    method: "GET",
    headers: DEFAULT_HEADERS,
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`API Error [${res.status}] on ${endpoint}`);
  }

  const data = await res.json();
  if (useCache) {
    memoryCache.set(url, { data, timestamp: Date.now() });
  }
  return data as T;
}

/** Prefetch full stock intelligence bundle on row hover or arrow navigation */
export function prefetchStockBundle(symbol: string) {
  const sym = symbol.toUpperCase();
  void apiFetch(`/stocks/${sym}/history`).catch(() => {});
  void apiFetch(`/stocks/${sym}/memo`).catch(() => {});
  void apiFetch(`/stocks/${sym}/forecast`).catch(() => {});
  void apiFetch(`/stocks/${sym}/news`).catch(() => {});
}

// ─── Shared Type Definitions ──────────────────────────────────────────────────

export interface ScreenerCandidate {
  rank: number;
  symbol: string;
  company_name: string;
  sector: string;
  close: number | null;
  sma_200: number | null;
  debt_to_equity: number | null;
  roe_pct: number | null;
  opm_pct: number | null;
  excess_ret_20d: number | null;
  composite_score: number | null;
  price_above_sma200: boolean | number;
  is_watchlist: boolean | number;
}

export interface ScreenerResponse {
  as_of_date: string;
  total_candidates: number;
  returned_count: number;
  results: ScreenerCandidate[];
}

export interface WatchlistItem {
  symbol: string;
  company_name: string;
  sector: string;
  close: number | null;
  ret_1d_pct: number | null;
  sma_200: number | null;
  dist_sma200_pct: number | null;
  price_above_sma200: boolean | number;
  roe_pct: number | null;
  debt_to_equity: number | null;
  opm_pct: number | null;
  ttm_pe: number | null;
  volatility_annualized: number | null;
}

export interface WatchlistResponse {
  count: number;
  watchlist: WatchlistItem[];
}

export interface SystemAccuracy {
  forecast_model: {
    total_evaluated: number;
    containment_80_pct: number;
    containment_95_pct: number;
    rmse_pct: number;
    mape_pct: number;
    target_benchmark_80: number;
    target_benchmark_95: number;
    status: string;
  };
  catalyst_model: {
    total_evaluated: number;
    directional_accuracy_pct: number;
    avg_5d_return_pct: number;
    status: string;
  };
  evaluated_at: string;
}

export interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ProjectionStep {
  step: number;
  target_date: string;
  expected: number;
  upper_80: number;
  lower_80: number;
  upper_95: number;
  lower_95: number;
}

export interface ForecastData {
  symbol: string;
  as_of_date: string;
  current_close: number;
  annualized_volatility: number;
  volatility_regime: "LOW" | "NORMAL" | "ELEVATED";
  forecast_horizon_days: number;
  garch_parameters?: {
    omega: number;
    alpha: number;
    beta: number;
    persistence: number;
  };
  mean_reversion_anchor?: number;
  projections: ProjectionStep[];
}

export type VerdictType =
  | "STRONG_BUY_COMPOUNDER"
  | "TACTICAL_SWING_LONG"
  | "HOLD_FAIRLY_VALUED"
  | "AVOID_CAPITAL_PRESERVATION";

export interface DiagnosticItem {
  id: string;
  name: string;
  status: "PASS" | "CAUTION" | "FAIL";
  detail: string;
}

export interface InvestmentMemo {
  symbol: string;
  company_name: string;
  as_of_date: string;
  verdict: VerdictType;
  target_horizon: string;
  institutional_conviction_score: number;
  business_profile: {
    sector: string;
    industry: string;
    macro_sector: string;
    operating_segments: string;
    core_revenue_drivers: string;
    geographic_concentration: string;
  };
  bull_case: string[];
  bear_case: string[];
  health_checklist: DiagnosticItem[];
  key_metrics: {
    current_price: number;
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    ttm_pe: number | null;
    roe_pct: number | null;
    debt_to_equity: number | null;
    opm_pct: number | null;
    beta_60d_nifty: number | null;
    volatility_annualized: number | null;
  };
  forecast_cone_summary?: {
    expected_20d_price: number;
    upper_80: number;
    lower_80: number;
    upper_95: number;
    lower_95: number;
    upside_pct: number;
  };
  recent_news_count?: number;
  generated_at: string;
}

export interface NewsImpact {
  direction: "BULLISH" | "BEARISH" | "NEUTRAL" | string;
  horizon: "SHORT_TERM" | "MEDIUM_TERM" | string;
  affected_drivers: string[];
  rationale: string;
  confidence_score?: number;
}

export interface NewsArticle {
  id: string;
  title: string;
  source: string;
  published_at: string;
  article_url: string;
  summary: string[];
  impact: NewsImpact;
}

export interface NewsResponse {
  symbol: string;
  article_count: number;
  articles: NewsArticle[];
}
