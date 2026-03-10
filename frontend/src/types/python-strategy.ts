// Python Strategy types

export interface PythonStrategy {
  id: string;
  name: string;
  description: string | null;
  code: string;
  status: "draft" | "backtesting" | "completed" | "error";
  backtest_config: BacktestConfig | null;
  backtest_result: BacktestStoredResult | null;
  backtest_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BacktestConfig {
  symbol: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  commission_rate: number;
}

export interface BacktestStoredResult {
  metrics: BacktestMetrics | null;
  equity_curve: [string, number][] | null;
  trades: BacktestTrade[] | null;
}

export interface BacktestMetrics {
  total_return_pct: number;
  annual_return_pct: number | null;
  max_drawdown_pct: number;
  sharpe_ratio: number | null;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  initial_capital: number;
  final_value: number;
  profit_loss: number;
}

export interface BacktestTrade {
  date: string;
  action: "BUY" | "SELL";
  symbol: string;
  price: number;
  shares: number;
  value: number;
  commission: number;
}

export interface BacktestRequest {
  strategy_id: string;
  symbol: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  commission_rate: number;
}

export interface BacktestResultData {
  strategy_id: string;
  success: boolean;
  metrics: BacktestMetrics | null;
  equity_curve: [string, number][] | null;
  trades: BacktestTrade[] | null;
  message: string;
  chart: string | null;
}

export interface CreatePythonStrategy {
  name: string;
  description?: string;
  code: string;
}

export interface UpdatePythonStrategy {
  name?: string;
  description?: string;
  code?: string;
}
