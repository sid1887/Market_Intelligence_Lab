/**
 * Market Intelligence Lab — Unified Zero-Latency API Client & Prefetch Cache
 * Workstream 5.3 — Monotonic request lifecycle, typed models, and robust error unwrapping
 */

export function getApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  return raw.endsWith("/api/v1") ? raw : `${raw.replace(/\/$/, "")}/api/v1`;
}

export const API_BASE = getApiBase();

export const DEFAULT_HEADERS: Record<string, string> = {
  "Accept": "application/json",
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details?: Record<string, unknown>;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || `API Error: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code || "UNKNOWN_ERROR";
    this.details = payload.details;
  }
}

export class RequestLifecycleManager {
  private activeControllers: Map<string, AbortController> = new Map();
  private requestGenerations: Map<string, number> = new Map();

  /**
   * Cancels any pending request for a given key and returns an active signal
   * along with a monotonic generation ID to prevent out-of-order race conditions.
   */
  public prepareRequest(key: string): { signal: AbortSignal; generation: number } {
    const existing = this.activeControllers.get(key);
    if (existing) {
      existing.abort();
    }

    const controller = new AbortController();
    this.activeControllers.set(key, controller);

    const nextGen = (this.requestGenerations.get(key) || 0) + 1;
    this.requestGenerations.set(key, nextGen);

    return { signal: controller.signal, generation: nextGen };
  }

  public isLatest(key: string, generation: number): boolean {
    return this.requestGenerations.get(key) === generation;
  }

  public cleanup(key: string) {
    const existing = this.activeControllers.get(key);
    if (existing) {
      existing.abort();
      this.activeControllers.delete(key);
    }
  }
}

export const requestLifecycle = new RequestLifecycleManager();

// In-memory cache for zero-latency stock switching
const memoryCache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL_MS = 60_000; // 60 seconds

// In-flight request deduplication (prevents redundant fetches on fast arrow scrubbing)
const inFlightRequests = new Map<string, Promise<unknown>>();

export interface ApiFetchOptions extends RequestInit {
  useCache?: boolean;
}

/**
 * Standardized typed fetch wrapper with AbortSignal, in-flight deduplication, and structured ApiError mapping.
 */
export async function apiFetch<T>(
  endpoint: string,
  optionsOrUseCache: ApiFetchOptions | boolean = true
): Promise<T> {
  const options: ApiFetchOptions =
    typeof optionsOrUseCache === "boolean"
      ? { useCache: optionsOrUseCache }
      : optionsOrUseCache;

  const useCache = options.useCache ?? (options.method === undefined || options.method === "GET");
  const normalizedEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${getApiBase()}${normalizedEndpoint}`;

  // 1. Check valid memory cache (only for GET without custom signal/body)
  if (useCache && !options.signal && !options.body && memoryCache.has(url)) {
    const cached = memoryCache.get(url)!;
    if (Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return cached.data as T;
    }
  }

  // 2. Reuse in-flight request if one is already pending and no custom signal is provided
  if (!options.signal && inFlightRequests.has(url)) {
    return inFlightRequests.get(url) as Promise<T>;
  }

  const headers: Record<string, string> = {
    ...DEFAULT_HEADERS,
    ...((options.headers as Record<string, string>) || {}),
  };

  const fetchPromise = (async () => {
    try {
      const res = await fetch(url, {
        cache: "no-store",
        ...options,
        headers,
      });

      if (!res.ok) {
        let errorPayload: ApiErrorPayload;
        try {
          const json = await res.json();
          errorPayload = json.error || {
            code: `HTTP_${res.status}`,
            message: json.detail || json.message || res.statusText,
            retryable: res.status >= 500,
          };
        } catch {
          errorPayload = {
            code: `HTTP_${res.status}`,
            message: res.statusText || `HTTP error ${res.status}`,
            retryable: res.status >= 500,
          };
        }
        throw new ApiError(res.status, errorPayload);
      }

      const data = (await res.json()) as T;
      if (useCache && !options.signal) {
        memoryCache.set(url, { data, timestamp: Date.now() });
      }
      return data;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        throw err; // Re-throw aborts for caller-level handling
      }
      if (err instanceof ApiError) {
        throw err;
      }
      const message = err instanceof Error ? err.message : "Network transport failure";
      throw new ApiError(0, {
        code: "NETWORK_FAILURE",
        message,
        retryable: true,
      });
    } finally {
      if (!options.signal) {
        inFlightRequests.delete(url);
      }
    }
  })();

  if (!options.signal) {
    inFlightRequests.set(url, fetchPromise);
  }

  return fetchPromise;
}

/**
 * Prefetch lightweight stock data on row hover or arrow navigation.
 * CQRS & UI Honesty: Does NOT prefetch expensive /memo or /forecast endpoints on hover.
 */
export function prefetchStockBundle(symbol: string) {
  if (!symbol) return;
  const sym = symbol.toUpperCase().trim();
  // Only lightweight history cache prefetch
  void apiFetch(`/stocks/${sym}/history`).catch(() => {});
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
  blended_score?: number | null;
  target_allocation_pct?: number | null;
  horizon_drivers?: string[];
  is_rebalance_target?: boolean | number;
  score_20d?: number | null;
  score_60d?: number | null;
  data_completeness_score?: number | null;
  score_status?: string | null;
  price_above_sma200: boolean | number;
  is_watchlist: boolean | number;
}

export interface TradeDelta {
  symbol: string;
  current_weight: number;
  target_weight: number;
  target_allocation_pct?: number;
  current_allocation_pct?: number;
  delta: number;
  delta_pct?: number;
  action: "BUY" | "SELL" | "HOLD";
  blended_score?: number | null;
}

export interface RebalanceProposalResponse {
  proposal_id: string | null;
  session_date: string | null;
  model_composite_id: string | null;
  status: string;
  turnover_pct: number;
  projected_cost_bps: number;
  holdings_before: Record<string, number>;
  holdings_after: Record<string, number>;
  trade_deltas: TradeDelta[];
  active_horizons: number[];
  effective_weights: Record<string, number>;
  created_at?: string;
  message?: string;
}

export async function fetchLatestRebalanceProposal(signal?: AbortSignal): Promise<RebalanceProposalResponse> {
  return apiFetch<RebalanceProposalResponse>("/rebalance/latest", { signal });
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
    containment_80_pct: number | null;
    containment_95_pct: number | null;
    rmse_pct: number | null;
    mape_pct: number | null;
    target_benchmark_80: number;
    target_benchmark_95: number;
    status: string;
  };
  catalyst_model: {
    total_evaluated: number;
    directional_accuracy_pct: number | null;
    avg_5d_return_pct: number | null;
    status: string;
  };
  evaluated_at?: string;
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

export interface MacroIndicator {
  symbol: string;
  label: string;
  value: number | null;
  unit: string;
  change_pct: number | null;
  source: string;
  observed_at?: string | null;
  freshness_status?: string;
}

export interface MacroResponse {
  status: string;
  timestamp?: string;
  retrieval_timestamp?: string;
  as_of_session?: string;
  indicators: MacroIndicator[];
}

export async function fetchMacroTelemetry(): Promise<MacroResponse> {
  return apiFetch<MacroResponse>("/macro");
}

export interface SupervisorStatus {
  status: string;
  supervisor_state: string;
  active_model_id?: string | null;
  model_name?: string | null;
  latest_settled_session: string;
  total_active_equities: number;
  universe_health_pct: number;
  last_ingestion_timestamp: string;
  daemon_started_at: string | null;
  macro_indicators?: MacroIndicator[];
}

export async function fetchSupervisorStatus(): Promise<SupervisorStatus> {
  return apiFetch<SupervisorStatus>("/supervisor/status");
}

export async function fetchStockTearsheet<T = unknown>(
  symbol: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  return apiFetch<T>(`/stocks/${symbol.toUpperCase()}/tearsheet`, options);
}

export async function fetchStockForecast(
  symbol: string,
  options: ApiFetchOptions = {}
): Promise<ForecastData> {
  return apiFetch<ForecastData>(`/stocks/${symbol.toUpperCase()}/forecast?horizon_days=20`, options);
}

export async function fetchDisclosures<T = unknown>(
  symbol: string,
  options: ApiFetchOptions = {}
): Promise<T[]> {
  return apiFetch<T[]>(`/stocks/${symbol.toUpperCase()}/disclosures`, options);
}

export async function fetchScreener(
  limit = 250,
  options: ApiFetchOptions = {}
): Promise<ScreenerResponse> {
  return apiFetch<ScreenerResponse>(`/screener?limit=${limit}`, options);
}

export interface IngestResponse {
  status: string;
  settled_date?: string;
  symbols_updated?: number;
  records_ingested?: number;
  factors_computed?: number;
  duration_seconds?: number;
  message: string;
}

export function clearMemoryCache() {
  memoryCache.clear();
}

export interface JobSubmissionRequest {
  job_type: "UNIVERSE_EOD" | "MODEL_TOURNAMENT" | "FACTOR_RECOMPUTE" | string;
  payload?: Record<string, unknown>;
  priority?: number;
  idempotency_key?: string;
}

export interface JobSubmissionResponse {
  job_id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  idempotency_key: string;
  poll_url: string;
  stream_url: string;
  message: string;
}

export interface JobRun {
  job_id: string;
  job_type: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  priority: number;
  idempotency_key: string;
  worker_id: string | null;
  progress_pct: number;
  current_stage: string | null;
  stage_message: string | null;
  items_total: number;
  items_processed: number;
  items_failed: number;
  attempt_count: number;
  max_retries: number;
  error_detail: string | null;
  result_payload: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  lease_expires_at: string | null;
}

export interface JobEventPayload {
  job_id: string;
  status: string;
  progress_pct: number;
  stage?: string;
  message?: string;
  processed?: number;
  total?: number;
  result?: Record<string, unknown>;
  error?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export async function submitJob(req: JobSubmissionRequest): Promise<JobSubmissionResponse> {
  const url = `${API_BASE}/jobs`;
  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(req),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to submit job: HTTP ${res.status}`);
  }
  return (await res.json()) as JobSubmissionResponse;
}

export async function getJob(jobId: string): Promise<JobRun> {
  const url = `${API_BASE}/jobs/${encodeURIComponent(jobId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: DEFAULT_HEADERS,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch job ${jobId}: HTTP ${res.status}`);
  }
  return (await res.json()) as JobRun;
}

export function getEventStreamUrl(jobId?: string): string {
  const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
  return `${API_BASE}/events/stream${query}`;
}

export async function triggerSystemIngest(): Promise<IngestResponse> {
  const url = `${API_BASE}/system/ingest`;
  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Ingest failed: HTTP ${res.status}`);
  }
  const data = (await res.json()) as IngestResponse;
  clearMemoryCache();
  return data;
}

// ─── Paper Trading Portfolio Types & Client API ───────────────────────────────

export interface PortfolioSummary {
  account_id: string;
  cash_balance: number;
  invested_value: number;
  total_nav: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  total_pnl: number;
  total_pnl_pct: number;
  total_friction_paid: number;
  positions_count: number;
  updated_at: string;
}

export interface PortfolioPosition {
  position_id: string;
  symbol: string;
  quantity: number;
  average_entry_price: number;
  current_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight_pct: number;
  updated_at: string;
}

export interface PortfolioOrder {
  order_id: string;
  account_id: string;
  proposal_id: string;
  symbol: string;
  action: "BUY" | "SELL";
  quantity: number;
  fill_price: number;
  friction_paid: number;
  executed_at: string;
}

export interface PortfolioExecuteResponse {
  proposal_id: string;
  account_id: string;
  status: string;
  orders_count: number;
  orders: Array<{
    order_id: string;
    symbol: string;
    action: "BUY" | "SELL";
    quantity: number;
    requested_quantity?: number;
    fill_price: number;
    gross_value: number;
    friction_paid: number;
    net_proceeds?: number;
    net_debit?: number;
    was_capped?: boolean;
  }>;
  total_friction_paid: number;
  cash_balance: number;
  invested_value: number;
  total_nav: number;
  executed_at: string;
}

export async function fetchPortfolioSummary(
  accountId = "paper_alpha_1",
  options: ApiFetchOptions = {}
): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>(`/portfolio/summary?account_id=${encodeURIComponent(accountId)}`, options);
}

export async function fetchPortfolioPositions(
  accountId = "paper_alpha_1",
  options: ApiFetchOptions = {}
): Promise<PortfolioPosition[]> {
  return apiFetch<PortfolioPosition[]>(`/portfolio/positions?account_id=${encodeURIComponent(accountId)}`, options);
}

export async function fetchPortfolioOrders(
  accountId = "paper_alpha_1",
  limit = 100,
  options: ApiFetchOptions = {}
): Promise<PortfolioOrder[]> {
  return apiFetch<PortfolioOrder[]>(`/portfolio/orders?account_id=${encodeURIComponent(accountId)}&limit=${limit}`, options);
}

export async function executePortfolioProposal(
  proposalId?: string,
  accountId = "paper_alpha_1"
): Promise<PortfolioExecuteResponse> {
  const url = `${API_BASE}/portfolio/execute`;
  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify({ proposal_id: proposalId || null, account_id: accountId }),
    cache: "no-store",
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Execution failed (${res.status}): ${errorText}`);
  }
  clearMemoryCache();
  return (await res.json()) as PortfolioExecuteResponse;
}

// ─── Systematic Portfolio Backtest Types & Client API ──────────────────────────

export interface BacktestSummaryMetrics {
  initial_capital: number;
  final_nav: number;
  total_return_pct: number;
  benchmark_return_pct: number;
  alpha_pct: number;
  cagr_pct: number;
  benchmark_cagr_pct?: number;
  alpha_cagr_pct?: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  calmar_ratio: number;
  win_rate_pct: number;
  total_rebalances: number;
  total_trades: number;
  total_friction_paid: number;
  friction_drag_bps: number;
  start_date: string;
  end_date: string;
  trading_sessions: number;
  strategy_mode: string;
  top_n: number;
  rebalance_every_n_days: number;
  rebalance_cadence?: number;
}

export interface BacktestEquityCurvePoint {
  date: string;
  trading_date?: string;
  nav: number;
  strategy_nav?: number;
  portfolio_value?: number;
  benchmark_nav: number;
  benchmark_value?: number;
  cash: number;
  cash_balance?: number;
  drawdown_pct: number;
  benchmark_drawdown_pct: number;
}

export interface BacktestRebalanceLogEntry {
  date: string;
  nav?: number;
  nav_before: number;
  nav_after: number;
  turnover_pct: number;
  orders_count: number;
  friction_paid: number;
  top_holdings: string[];
  holdings_count: number;
}

export interface PortfolioBacktestResponse {
  summary_metrics: BacktestSummaryMetrics;
  equity_curve: BacktestEquityCurvePoint[];
  rebalance_log: BacktestRebalanceLogEntry[];
}

export interface BacktestPresetsResponse {
  strategy_modes: Array<{ id: string; name: string; description: string }>;
  top_n_options: number[];
  frequency_options: Array<{ label: string; value: number }>;
  default_config: {
    initial_capital: number;
    top_n: number;
    rebalance_every_n_days: number;
    rebalance_cadence?: number;
    strategy_mode: string;
    start_date: string;
    end_date: string;
  };
  date_bounds: { start_date: string; end_date: string };
}

export interface BacktestRequestPayload {
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  top_n?: number;
  rebalance_every_n_days?: number;
  rebalance_cadence?: number;
  strategy_mode?: string;
}

export async function fetchBacktestPresets(): Promise<BacktestPresetsResponse> {
  return apiFetch<BacktestPresetsResponse>("/backtest/presets", { useCache: false });
}

export async function runPortfolioBacktest(
  payload: BacktestRequestPayload
): Promise<PortfolioBacktestResponse> {
  const url = `${API_BASE}/backtest/run`;
  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Backtest simulation failed (${res.status}): ${errorText}`);
  }
  return (await res.json()) as PortfolioBacktestResponse;
}

export interface MultiStockCompareRequestPayload {
  symbols: string[];
  start_date?: string;
  end_date?: string;
  benchmark_symbol?: string;
}

export interface StockComparisonMetric {
  symbol: string;
  total_return_pct: number;
  cagr_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  beta_to_bench: number;
}

export interface MultiStockCompareResponse {
  start_date: string;
  end_date: string;
  benchmark_symbol: string;
  symbols: string[];
  normalized_series: Array<Record<string, string | number>>;
  comparison_metrics: Record<string, StockComparisonMetric>;
  correlation_matrix: Record<string, Record<string, number>>;
  radar_scores: Record<string, { quality: number; momentum: number; trend: number; volatility: number }>;
}

export async function runMultiStockComparison(
  payload: MultiStockCompareRequestPayload
): Promise<MultiStockCompareResponse> {
  const url = `${API_BASE}/backtest/compare`;
  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Comparison failed (${res.status}): ${errorText}`);
  }
  return (await res.json()) as MultiStockCompareResponse;
}

