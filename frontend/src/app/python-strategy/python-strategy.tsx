import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  useCreatePythonStrategy,
  useDeletePythonStrategy,
  useGetPythonStrategies,
  useRunBacktest,
  useUpdatePythonStrategy,
} from "@/api/python-strategy";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  BacktestResultData,
  PythonStrategy,
} from "@/types/python-strategy";
import {
  Code2,
  FileText,
  Loader2,
  Play,
  Plus,
  Save,
  Trash2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

const DEFAULT_CODE = `"""My Strategy

Define a \`strategy(ctx)\` function that is called on each bar.

ctx attributes:
  ctx.date       - current bar date string (YYYY-MM-DD)
  ctx.open       - open price
  ctx.high       - high price
  ctx.low        - low price
  ctx.close      - close price
  ctx.volume     - volume
  ctx.position   - current shares held
  ctx.cash       - available cash
  ctx.portfolio_value - total portfolio value
  ctx.history    - DataFrame of all bars up to now

ctx methods:
  ctx.buy(shares=None)   - buy shares (None = max affordable)
  ctx.sell(shares=None)  - sell shares (None = sell all)

Available modules: math, pd (pandas)
"""


def strategy(ctx):
    # Simple moving-average crossover example
    if len(ctx.history) < 20:
        return

    closes = ctx.history["Close"]
    sma5 = closes.iloc[-5:].mean()
    sma20 = closes.iloc[-20:].mean()

    if sma5 > sma20 and ctx.position == 0:
        ctx.buy()
    elif sma5 < sma20 and ctx.position > 0:
        ctx.sell()
`;

export default function PythonStrategyPage() {
  const { data: strategies, isLoading } = useGetPythonStrategies();
  const createMutation = useCreatePythonStrategy();
  const updateMutation = useUpdatePythonStrategy();
  const deleteMutation = useDeletePythonStrategy();
  const backtestMutation = useRunBacktest();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [code, setCode] = useState(DEFAULT_CODE);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [activeTab, setActiveTab] = useState("editor");

  // Backtest config
  const [symbol, setSymbol] = useState("AAPL");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2025-01-01");
  const [initialCapital, setInitialCapital] = useState(100000);
  const [commissionRate, setCommissionRate] = useState(0.001);

  // Backtest result
  const [backtestResult, setBacktestResult] =
    useState<BacktestResultData | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const selectedStrategy = useMemo(
    () => strategies?.find((s) => s.id === selectedId) ?? null,
    [strategies, selectedId],
  );

  // Load strategy into editor
  const loadStrategy = useCallback((s: PythonStrategy) => {
    setSelectedId(s.id);
    setCode(s.code);
    setName(s.name);
    setDescription(s.description ?? "");
    if (s.backtest_config) {
      setSymbol(s.backtest_config.symbol);
      setStartDate(s.backtest_config.start_date);
      setEndDate(s.backtest_config.end_date);
      setInitialCapital(s.backtest_config.initial_capital);
      setCommissionRate(s.backtest_config.commission_rate);
    }
    if (s.backtest_result?.metrics) {
      setBacktestResult({
        strategy_id: s.id,
        success: true,
        metrics: s.backtest_result.metrics,
        equity_curve: s.backtest_result.equity_curve,
        trades: s.backtest_result.trades,
        message: "",
        chart: null,
      });
      setActiveTab("result");
    } else {
      setBacktestResult(null);
      setActiveTab("editor");
    }
  }, []);

  // Auto-select first strategy
  useEffect(() => {
    if (!selectedId && strategies && strategies.length > 0) {
      loadStrategy(strategies[0]);
    }
  }, [strategies, selectedId, loadStrategy]);

  const handleCreate = async () => {
    const stratName = `Strategy ${(strategies?.length ?? 0) + 1}`;
    const result = await createMutation.mutateAsync({
      name: stratName,
      code: DEFAULT_CODE,
    });
    if (result.data) {
      loadStrategy(result.data);
      toast.success("Strategy created");
    }
  };

  const handleSave = async () => {
    if (!selectedId) return;
    await updateMutation.mutateAsync({
      id: selectedId,
      data: { name, description: description || undefined, code },
    });
    toast.success("Strategy saved");
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    await deleteMutation.mutateAsync(selectedId);
    setSelectedId(null);
    setBacktestResult(null);
    toast.success("Strategy deleted");
  };

  const handleBacktest = async () => {
    if (!selectedId) {
      toast.error("Please save the strategy first");
      return;
    }
    // Save first
    await updateMutation.mutateAsync({
      id: selectedId,
      data: { name, description: description || undefined, code },
    });

    const result = await backtestMutation.mutateAsync({
      strategy_id: selectedId,
      symbol,
      start_date: startDate,
      end_date: endDate,
      initial_capital: initialCapital,
      commission_rate: commissionRate,
    });
    setBacktestResult(result.data);
    if (result.data.success) {
      setActiveTab("result");
      toast.success("Backtest completed");
    } else {
      toast.error(result.data.message || "Backtest failed");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Tab support in textarea
    if (e.key === "Tab") {
      e.preventDefault();
      const ta = e.currentTarget;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const newCode = `${code.substring(0, start)}    ${code.substring(end)}`;
      setCode(newCode);
      requestAnimationFrame(() => {
        ta.selectionStart = start + 4;
        ta.selectionEnd = start + 4;
      });
    }
    // Ctrl+S to save
    if (e.key === "s" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <Code2 className="size-5 text-primary" />
          <h1 className="font-semibold text-lg">Python Strategy Lab</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleCreate}>
            <Plus className="size-4" />
            New
          </Button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar - Strategy list */}
        <div className="w-56 shrink-0 overflow-y-auto border-r bg-muted/30">
          <div className="p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground uppercase">
              Strategies
            </p>
            {isLoading && (
              <p className="text-xs text-muted-foreground">Loading...</p>
            )}
            {strategies?.map((s) => (
              <button
                type="button"
                key={s.id}
                onClick={() => loadStrategy(s)}
                className={`mb-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                  selectedId === s.id
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-foreground"
                }`}
              >
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{s.name}</span>
                <span
                  className={`ml-auto inline-block size-2 rounded-full shrink-0 ${
                    s.status === "completed"
                      ? "bg-green-500"
                      : s.status === "error"
                        ? "bg-red-500"
                        : s.status === "backtesting"
                          ? "bg-yellow-500"
                          : "bg-gray-400"
                  }`}
                />
              </button>
            ))}
            {strategies && strategies.length === 0 && (
              <p className="text-xs text-muted-foreground mt-4 text-center">
                No strategies yet. Click "New" to create one.
              </p>
            )}
          </div>
        </div>

        {/* Main content */}
        <div className="flex flex-1 min-w-0 flex-col">
          {selectedId ? (
            <>
              {/* Strategy name and actions */}
              <div className="flex items-center gap-3 border-b px-4 py-2">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="h-8 w-56 text-sm font-medium"
                  placeholder="Strategy name"
                />
                <Input
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="h-8 flex-1 text-sm"
                  placeholder="Description (optional)"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={updateMutation.isPending}
                >
                  <Save className="size-3.5" />
                  Save
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>

              <Tabs
                value={activeTab}
                onValueChange={setActiveTab}
                className="flex flex-1 min-h-0 flex-col"
              >
                <div className="flex items-center justify-between border-b px-4">
                  <TabsList className="h-9">
                    <TabsTrigger value="editor">Code Editor</TabsTrigger>
                    <TabsTrigger value="result">
                      Backtest Result
                      {backtestResult?.success && (
                        <span className="ml-1.5 inline-block size-1.5 rounded-full bg-green-500" />
                      )}
                    </TabsTrigger>
                  </TabsList>

                  {/* Backtest config inline */}
                  <div className="flex items-center gap-2">
                    <Input
                      value={symbol}
                      onChange={(e) => setSymbol(e.target.value)}
                      className="h-7 w-20 text-xs"
                      placeholder="Symbol"
                    />
                    <Input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="h-7 w-32 text-xs"
                    />
                    <Input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="h-7 w-32 text-xs"
                    />
                    <Input
                      type="number"
                      value={initialCapital}
                      onChange={(e) =>
                        setInitialCapital(Number(e.target.value))
                      }
                      className="h-7 w-24 text-xs"
                      placeholder="Capital"
                    />
                    <Button
                      size="sm"
                      onClick={handleBacktest}
                      disabled={backtestMutation.isPending}
                      className="h-7 gap-1 px-3 text-xs"
                    >
                      {backtestMutation.isPending ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Play className="size-3" />
                      )}
                      Run Backtest
                    </Button>
                  </div>
                </div>

                {/* Editor tab */}
                <TabsContent value="editor" className="flex-1 min-h-0 p-0">
                  <div className="relative h-full">
                    <textarea
                      ref={textareaRef}
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      onKeyDown={handleKeyDown}
                      spellCheck={false}
                      className="h-full w-full resize-none border-0 bg-[#1e1e2e] p-4 font-mono text-sm text-[#cdd6f4] outline-none"
                      style={{ tabSize: 4 }}
                    />
                  </div>
                </TabsContent>

                {/* Result tab */}
                <TabsContent
                  value="result"
                  className="flex-1 min-h-0 overflow-y-auto p-4"
                >
                  {backtestResult ? (
                    <BacktestResults data={backtestResult} />
                  ) : (
                    <div className="flex h-full items-center justify-center text-muted-foreground">
                      Run a backtest to see results here.
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              Select a strategy or create a new one to get started.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Backtest Results Component ----
function BacktestResults({ data }: { data: BacktestResultData }) {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!data.equity_curve || !chartRef.current) return;

    let disposed = false;

    import("echarts").then((echarts) => {
      if (disposed || !chartRef.current) return;

      const chart = echarts.init(chartRef.current);

      const dates = data.equity_curve!.map((p) => p[0]);
      const values = data.equity_curve!.map((p) => p[1]);

      chart.setOption({
        tooltip: {
          trigger: "axis",
          formatter: (params: unknown) => {
            const p = (params as { data: number; axisValue: string }[])[0];
            return `${p.axisValue}<br/>Portfolio: $${p.data.toLocaleString()}`;
          },
        },
        xAxis: {
          type: "category",
          data: dates,
          axisLabel: { rotate: 45, fontSize: 10 },
        },
        yAxis: {
          type: "value",
          axisLabel: {
            formatter: (v: number) => `$${(v / 1000).toFixed(0)}k`,
          },
        },
        series: [
          {
            data: values,
            type: "line",
            smooth: true,
            lineStyle: { color: "#42A5F5", width: 2 },
            areaStyle: {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "rgba(66,165,245,0.3)" },
                  { offset: 1, color: "rgba(66,165,245,0.02)" },
                ],
              },
            },
            symbol: "none",
          },
        ],
        grid: { left: 60, right: 20, top: 20, bottom: 60 },
      });

      const onResize = () => chart.resize();
      window.addEventListener("resize", onResize);

      return () => {
        window.removeEventListener("resize", onResize);
        chart.dispose();
      };
    });

    return () => {
      disposed = true;
    };
  }, [data.equity_curve]);

  if (!data.success) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Backtest Failed</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="whitespace-pre-wrap rounded bg-muted p-3 text-sm font-mono">
            {data.message}
          </pre>
        </CardContent>
      </Card>
    );
  }

  const m = data.metrics;
  if (!m) return null;

  return (
    <div className="flex flex-col gap-4">
      {/* Metrics cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Total Return"
          value={`${m.total_return_pct >= 0 ? "+" : ""}${m.total_return_pct.toFixed(2)}%`}
          positive={m.total_return_pct >= 0}
        />
        <MetricCard
          label="Annualised Return"
          value={
            m.annual_return_pct != null
              ? `${m.annual_return_pct >= 0 ? "+" : ""}${m.annual_return_pct.toFixed(2)}%`
              : "N/A"
          }
          positive={(m.annual_return_pct ?? 0) >= 0}
        />
        <MetricCard
          label="Max Drawdown"
          value={`-${m.max_drawdown_pct.toFixed(2)}%`}
          positive={false}
        />
        <MetricCard
          label="Sharpe Ratio"
          value={m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(4) : "N/A"}
          positive={(m.sharpe_ratio ?? 0) > 0}
        />
        <MetricCard
          label="Win Rate"
          value={`${m.win_rate_pct.toFixed(1)}%`}
          positive={m.win_rate_pct >= 50}
        />
        <MetricCard
          label="Total Trades"
          value={String(m.total_trades)}
          positive
        />
        <MetricCard
          label="P&L"
          value={`${m.profit_loss >= 0 ? "+" : ""}$${m.profit_loss.toLocaleString()}`}
          positive={m.profit_loss >= 0}
        />
        <MetricCard
          label="Final Value"
          value={`$${m.final_value.toLocaleString()}`}
          positive={m.final_value >= m.initial_capital}
        />
      </div>

      {/* Equity curve chart */}
      {data.equity_curve && data.equity_curve.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Equity Curve</CardTitle>
          </CardHeader>
          <CardContent>
            <div ref={chartRef} className="h-64 w-full" />
          </CardContent>
        </Card>
      )}

      {/* Trade table */}
      {data.trades && data.trades.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Trade History</CardTitle>
            <CardDescription>
              {data.trades.length} trades
            </CardDescription>
          </CardHeader>
          <CardContent className="max-h-64 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Shares</TableHead>
                  <TableHead className="text-right">Value</TableHead>
                  <TableHead className="text-right">Commission</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.trades.map((t, i) => (
                  <TableRow key={`${t.date}-${t.action}-${i}`}>
                    <TableCell className="text-xs">{t.date}</TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${
                          t.action === "BUY"
                            ? "bg-green-500/10 text-green-600"
                            : "bg-red-500/10 text-red-600"
                        }`}
                      >
                        {t.action === "BUY" ? (
                          <TrendingUp className="size-3" />
                        ) : (
                          <TrendingDown className="size-3" />
                        )}
                        {t.action}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs font-medium">
                      {t.symbol}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      ${t.price.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      {t.shares}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      ${t.value.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      ${t.commission.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  positive,
}: {
  label: string;
  value: string;
  positive: boolean;
}) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 font-semibold text-lg ${positive ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
      >
        {value}
      </p>
    </div>
  );
}
