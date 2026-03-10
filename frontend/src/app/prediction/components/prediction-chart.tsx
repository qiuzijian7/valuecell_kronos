import {
  CandlestickChart as ECandlestickChart,
  LineChart,
} from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import type { ECharts } from "echarts/core";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts/types/dist/shared";
import { memo, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useChartResize } from "@/hooks/use-chart-resize";
import { useStockColors } from "@/store/settings-store";
import type { KronosPredictionResult } from "@/api/kronos";

echarts.use([
  ECandlestickChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  DataZoomComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

interface PredictionChartProps {
  predictionData: KronosPredictionResult;
  ticker: string;
  theme?: "light" | "dark";
  locale?: string;
}

function PredictionChart({
  predictionData,
  ticker,
  theme = "light",
  locale = "en",
}: PredictionChartProps) {
  const { t } = useTranslation();
  const bcp47Locale = locale.replace("_", "-");
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const stockColors = useStockColors();

  const option: EChartsOption = useMemo(() => {
    if (!predictionData?.prediction_results?.length) return {};

    const historical = predictionData.historical_data ?? [];
    const predictions = predictionData.prediction_results;
    const actuals = predictionData.actual_data ?? [];

    // Build date axis and data
    const allDates: string[] = [];
    const histKlineData: Array<[number, number, number, number]> = [];
    const predKlineData: Array<[number, number, number, number] | "-"> = [];
    const actualCloseData: Array<number | "-"> = [];

    // Historical data
    for (const bar of historical) {
      const dateStr = new Date(bar.timestamp).toLocaleDateString(bcp47Locale);
      allDates.push(dateStr);
      // ECharts candlestick: [open, close, low, high]
      histKlineData.push([bar.open, bar.close, bar.low, bar.high]);
      predKlineData.push("-");
      actualCloseData.push("-");
    }

    // Prediction data
    for (let i = 0; i < predictions.length; i++) {
      const pred = predictions[i];
      const dateStr = new Date(pred.timestamp).toLocaleDateString(bcp47Locale);
      allDates.push(dateStr);
      histKlineData.push([NaN, NaN, NaN, NaN]);
      predKlineData.push([pred.open, pred.close, pred.low, pred.high]);
      actualCloseData.push(actuals[i]?.close ?? "-");
    }

    const textColor = theme === "dark" ? "#ccc" : "#333";
    const bgColor = theme === "dark" ? "#1a1a2e" : "#ffffff";
    const predBoundaryIdx = historical.length;

    // Prediction colors — slightly different shade for distinction
    const predUpColor = "#66BB6A";
    const predDownColor = "#FF7043";

    const series: EChartsOption["series"] = [
      {
        name: t("prediction.historical", "历史数据"),
        type: "candlestick",
        data: histKlineData,
        itemStyle: {
          color: stockColors.positive,
          color0: stockColors.negative,
          borderColor: stockColors.positive,
          borderColor0: stockColors.negative,
        },
      },
      {
        name: t("prediction.predictionData", "预测数据"),
        type: "candlestick",
        data: predKlineData,
        itemStyle: {
          color: predUpColor,
          color0: predDownColor,
          borderColor: predUpColor,
          borderColor0: predDownColor,
        },
      },
    ];

    // Actual close line if comparison data exists
    if (actuals.length > 0) {
      series.push({
        name: t("prediction.actualClose", "实际收盘价"),
        type: "line",
        data: actualCloseData,
        smooth: false,
        lineStyle: { width: 2, color: "#FF9800", type: "dashed" },
        itemStyle: { color: "#FF9800" },
        symbol: "circle",
        symbolSize: 4,
        z: 10,
      } as EChartsOption["series"]);
    }

    // Calculate reasonable data zoom range
    const totalBars = allDates.length;
    const visibleBars = Math.min(totalBars, 120);
    const startPct = Math.max(0, ((totalBars - visibleBars) / totalBars) * 100);

    return {
      backgroundColor: bgColor,
      animation: true,
      animationDuration: 500,
      legend: {
        top: 0,
        left: "center",
        textStyle: { color: textColor, fontSize: 12 },
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        borderWidth: 1,
        borderColor: theme === "dark" ? "#444" : "#ccc",
        padding: 10,
        backgroundColor: theme === "dark" ? "#2a2a3e" : "#fff",
        textStyle: { color: textColor },
      },
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
        label: { backgroundColor: "#777" },
      },
      grid: [
        {
          left: "6%",
          right: "4%",
          top: "8%",
          height: "68%",
          containLabel: true,
        },
      ],
      xAxis: [
        {
          type: "category",
          data: allDates,
          boundaryGap: true,
          axisLine: { lineStyle: { color: textColor } },
          splitLine: { show: false },
          min: "dataMin",
          max: "dataMax",
          axisPointer: { z: 100 },
        },
      ],
      yAxis: [
        {
          scale: true,
          splitArea: {
            show: true,
            areaStyle: {
              color:
                theme === "dark"
                  ? ["rgba(255,255,255,0.02)", "rgba(255,255,255,0.05)"]
                  : ["rgba(0,0,0,0.02)", "rgba(0,0,0,0.05)"],
            },
          },
          axisLine: { lineStyle: { color: textColor } },
          splitLine: {
            lineStyle: {
              color:
                theme === "dark"
                  ? "rgba(255,255,255,0.1)"
                  : "rgba(0,0,0,0.1)",
            },
          },
        },
      ],
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: [0],
          start: startPct,
          end: 100,
        },
        {
          show: true,
          xAxisIndex: [0],
          type: "slider",
          top: "82%",
          height: 30,
          start: startPct,
          end: 100,
        },
      ],
      // Mark the prediction boundary with a vertical line
      ...(predBoundaryIdx > 0
        ? {}
        : {}),
      series: [
        ...series,
        // Invisible line series just for the markLine (boundary separator)
        {
          type: "line",
          data: [],
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: {
              color: theme === "dark" ? "#555" : "#bbb",
              type: "dashed",
              width: 2,
            },
            data: [
              {
                xAxis: allDates[predBoundaryIdx] ?? "",
                label: {
                  show: true,
                  formatter: t("prediction.predStart", "预测起点"),
                  position: "start",
                  color: theme === "dark" ? "#aaa" : "#666",
                  fontSize: 11,
                },
              },
            ],
          },
        } as EChartsOption["series"],
      ],
    };
  }, [predictionData, stockColors, theme, t, bcp47Locale]);

  useChartResize(chartInstance);

  useEffect(() => {
    if (!chartRef.current) return;
    chartInstance.current = echarts.init(chartRef.current);
    chartInstance.current.setOption(option);
    return () => {
      chartInstance.current?.dispose();
    };
  }, [option]);

  useEffect(() => {
    if (chartInstance.current) {
      chartInstance.current.setOption(option);
    }
  }, [option]);

  if (!predictionData) {
    return null;
  }

  const hasResults =
    predictionData.prediction_results &&
    predictionData.prediction_results.length > 0;

  return (
    <div className="flex flex-col gap-2">
      {/* Main ECharts candlestick chart */}
      {hasResults ? (
        <div ref={chartRef} className="w-full" style={{ height: 520 }} />
      ) : (
        <div className="flex h-[420px] w-full items-center justify-center rounded-lg border border-dashed border-border">
          <p className="text-muted-foreground">
            {t("prediction.noData", "暂无预测数据")}
          </p>
        </div>
      )}

      {/* Prediction vs Actual Comparison Table */}
      {hasResults && (
        <div className="rounded-lg border border-border">
          <div className="max-h-[200px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                    {t("prediction.time", "时间")}
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    {t("prediction.predOpen", "预测开盘")}
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    {t("prediction.predHigh", "预测最高")}
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    {t("prediction.predLow", "预测最低")}
                  </th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                    {t("prediction.predClose", "预测收盘")}
                  </th>
                  {predictionData.has_comparison && (
                    <>
                      <th className="px-3 py-2 text-right font-medium text-green-600">
                        {t("prediction.actualClose", "实际收盘")}
                      </th>
                      <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                        {t("prediction.errorPct", "误差%")}
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {predictionData.prediction_results
                  .slice(0, 20)
                  .map((pred, idx) => {
                    const actual = predictionData.actual_data?.[idx];
                    const errorPct = actual
                      ? (
                          ((pred.close - actual.close) / actual.close) *
                          100
                        ).toFixed(2)
                      : null;

                    return (
                      <tr
                        key={pred.timestamp}
                        className="border-t border-border hover:bg-muted/50"
                      >
                        <td className="px-3 py-2 text-foreground">
                          {new Date(pred.timestamp).toLocaleDateString(
                            bcp47Locale
                          )}
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

export default memo(PredictionChart);
