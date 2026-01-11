import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { KronosPredictionResult } from "@/api/kronos";

interface PredictionChartProps {
  predictionData: KronosPredictionResult;
  ticker: string;
  theme?: "light" | "dark";
  locale?: string;
}

// Track if Plotly is loaded globally
let plotlyLoaded = false;
let plotlyLoading = false;
const plotlyCallbacks: (() => void)[] = [];

function loadPlotly(): Promise<void> {
  return new Promise((resolve) => {
    if (plotlyLoaded && window.Plotly) {
      resolve();
      return;
    }

    if (plotlyLoading) {
      plotlyCallbacks.push(resolve);
      return;
    }

    plotlyLoading = true;
    const script = document.createElement("script");
    script.src = "https://cdn.plot.ly/plotly-2.27.0.min.js";
    script.async = true;

    script.onload = () => {
      plotlyLoaded = true;
      plotlyLoading = false;
      resolve();
      plotlyCallbacks.forEach((cb) => cb());
      plotlyCallbacks.length = 0;
    };

    script.onerror = () => {
      plotlyLoading = false;
      console.error("Failed to load Plotly");
    };

    document.head.appendChild(script);
  });
}

function PredictionChart({
  predictionData,
  ticker,
  theme = "light",
  locale = "en",
}: PredictionChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [plotlyReady, setPlotlyReady] = useState(plotlyLoaded);

  // Parse the chart data from prediction results
  const chartData = useMemo(() => {
    if (!predictionData?.chart) {
      console.log("No chart data available");
      return null;
    }
    try {
      const parsed = JSON.parse(predictionData.chart);
      console.log("Chart data parsed:", parsed);
      return parsed;
    } catch (e) {
      console.error("Failed to parse chart data:", e);
      return null;
    }
  }, [predictionData?.chart]);

  // Load Plotly once
  useEffect(() => {
    if (!plotlyReady) {
      loadPlotly().then(() => setPlotlyReady(true));
    }
  }, [plotlyReady]);

  // Render chart when data and Plotly are ready
  useEffect(() => {
    if (!containerRef.current || !chartData || !plotlyReady || !window.Plotly) {
      return;
    }

    console.log("Rendering Plotly chart...");

    // Update chart layout based on theme
    const updatedLayout = {
      ...chartData.layout,
      paper_bgcolor: theme === "dark" ? "#1f2937" : "#ffffff",
      plot_bgcolor: theme === "dark" ? "#1f2937" : "#ffffff",
      font: {
        color: theme === "dark" ? "#e5e7eb" : "#1f2937",
      },
      xaxis: {
        ...chartData.layout?.xaxis,
        gridcolor: theme === "dark" ? "#374151" : "#e5e7eb",
        rangeslider: { visible: false },
      },
      yaxis: {
        ...chartData.layout?.yaxis,
        gridcolor: theme === "dark" ? "#374151" : "#e5e7eb",
      },
    };

    try {
      window.Plotly.newPlot(
        containerRef.current,
        chartData.data,
        updatedLayout,
        {
          responsive: true,
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
        }
      );
      console.log("Plotly chart rendered successfully");
    } catch (e) {
      console.error("Failed to render Plotly chart:", e);
    }

    return () => {
      if (containerRef.current && window.Plotly) {
        window.Plotly.purge(containerRef.current);
      }
    };
  }, [chartData, theme, plotlyReady]);

  if (!predictionData) {
    return null;
  }

  // Show message if no chart but has prediction results
  const hasResults = predictionData.prediction_results && predictionData.prediction_results.length > 0;

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Main Chart */}
      {chartData ? (
        <div
          ref={containerRef}
          className="h-[420px] w-full rounded-lg border border-border bg-background"
          style={{ minHeight: "420px" }}
        />
      ) : hasResults ? (
        <div className="flex h-[420px] w-full items-center justify-center rounded-lg border border-dashed border-border bg-muted/30">
          <div className="text-center text-muted-foreground">
            <p className="mb-2">Chart visualization not available</p>
            <p className="text-sm">View prediction data in the table below</p>
          </div>
        </div>
      ) : (
        <div className="flex h-[420px] w-full items-center justify-center rounded-lg border border-dashed border-border">
          <p className="text-muted-foreground">No prediction data</p>
        </div>
      )}

      {/* Prediction vs Actual Comparison Table */}
      {predictionData.prediction_results && predictionData.prediction_results.length > 0 && (
        <div className="rounded-lg border border-border">
          <div className="max-h-[200px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                    Time
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Pred Open
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Pred High
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Pred Low
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    Pred Close
                  </th>
                  {predictionData.has_comparison && (
                    <>
                      <th className="px-3 py-2 text-right font-medium text-green-600">
                        Actual Close
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                        Error %
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {predictionData.prediction_results.slice(0, 20).map((pred, idx) => {
                  const actual = predictionData.actual_data?.[idx];
                  const errorPct = actual
                    ? (((pred.close - actual.close) / actual.close) * 100).toFixed(2)
                    : null;

                  return (
                    <tr
                      key={pred.timestamp}
                      className="border-t border-border hover:bg-muted/50"
                    >
                      <td className="px-3 py-2 text-foreground">
                        {new Date(pred.timestamp).toLocaleDateString(locale)}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">
                        {pred.open.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">
                        {pred.high.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">
                        {pred.low.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right text-foreground">
                        {pred.close.toFixed(2)}
                      </td>
                      {predictionData.has_comparison && (
                        <>
                          <td className="px-3 py-2 text-right text-green-600">
                            {actual?.close.toFixed(2) ?? "-"}
                          </td>
                          <td
                            className={`px-3 py-2 text-right ${
                              errorPct && Number(errorPct) > 0
                                ? "text-red-500"
                                : "text-green-500"
                            }`}
                          >
                            {errorPct ? `${errorPct}%` : "-"}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// Extend Window interface for Plotly
declare global {
  interface Window {
    Plotly: {
      newPlot: (
        element: HTMLElement,
        data: unknown[],
        layout: unknown,
        config: unknown
      ) => void;
      purge: (element: HTMLElement) => void;
    };
  }
}

export default memo(PredictionChart);
