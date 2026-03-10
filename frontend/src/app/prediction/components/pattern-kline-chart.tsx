import {
  CandlestickChart as ECandlestickChart,
  ScatterChart,
} from "echarts/charts";
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  MarkPointComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import type { ECharts } from "echarts/core";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts/types/dist/shared";
import { memo, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useChartResize } from "@/hooks/use-chart-resize";
import { useStockColors } from "@/store/settings-store";
import type { OHLCVBar, PatternMatchItem } from "@/api/kronos";

echarts.use([
  ECandlestickChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  DataZoomComponent,
  MarkPointComponent,
  LegendComponent,
  CanvasRenderer,
]);

interface PatternKlineChartProps {
  ohlcv: OHLCVBar[];
  patterns: PatternMatchItem[];
  height?: number;
  loading?: boolean;
  theme?: "light" | "dark";
}

const SENTIMENT_COLORS = {
  bullish: "#26A69A",
  bearish: "#EF5350",
  neutral: "#FFA726",
} as const;

const SENTIMENT_SYMBOLS = {
  bullish: "triangle",
  bearish: "pin",
  neutral: "diamond",
} as const;

function PatternKlineChart({
  ohlcv,
  patterns,
  height = 520,
  loading,
  theme = "light",
}: PatternKlineChartProps) {
  const { t } = useTranslation();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<ECharts | null>(null);
  const stockColors = useStockColors();

  const option: EChartsOption = useMemo(() => {
    if (!ohlcv || ohlcv.length === 0) return {};

    const dates = ohlcv.map((b) => b.date);
    // ECharts candlestick format: [open, close, low, high]
    const klineData = ohlcv.map((b) => [b.open, b.close, b.low, b.high]);

    const textColor = theme === "dark" ? "#ccc" : "#333";
    const bgColor = theme === "dark" ? "#1a1a2e" : "#ffffff";

    // Build pattern scatter data — show above/below bars
    const bullishData: Array<[string, number, string]> = [];
    const bearishData: Array<[string, number, string]> = [];
    const neutralData: Array<[string, number, string]> = [];

    for (const p of patterns) {
      const bar = ohlcv[p.index];
      if (!bar) continue;
      const entry: [string, number, string] = [
        bar.date,
        p.sentiment === "bearish" ? bar.high * 1.01 : bar.low * 0.99,
        p.label,
      ];
      if (p.sentiment === "bullish") {
        bullishData.push(entry);
      } else if (p.sentiment === "bearish") {
        bearishData.push(entry);
      } else {
        neutralData.push(entry);
      }
    }

    const series: EChartsOption["series"] = [
      {
        name: "K线",
        type: "candlestick",
        data: klineData,
        itemStyle: {
          color: stockColors.positive,
          color0: stockColors.negative,
          borderColor: stockColors.positive,
          borderColor0: stockColors.negative,
        },
      },
    ];

    // Add scatter series for each sentiment
    if (bullishData.length > 0) {
      series.push({
        name: t("prediction.bullishPattern", "看涨形态"),
        type: "scatter",
        coordinateSystem: "cartesian2d",
        data: bullishData.map((d) => ({
          value: [d[0], d[1]],
          name: d[2],
        })),
        symbol: "triangle",
        symbolSize: 14,
        symbolRotate: 0,
        itemStyle: { color: SENTIMENT_COLORS.bullish },
        label: {
          show: true,
          position: "bottom",
          formatter: (params: { name?: string }) => params.name ?? "",
          fontSize: 10,
          color: SENTIMENT_COLORS.bullish,
        },
        z: 10,
      } as EChartsOption["series"]);
    }

    if (bearishData.length > 0) {
      series.push({
        name: t("prediction.bearishPattern", "看跌形态"),
        type: "scatter",
        coordinateSystem: "cartesian2d",
        data: bearishData.map((d) => ({
          value: [d[0], d[1]],
          name: d[2],
        })),
        symbol: "pin",
        symbolSize: 14,
        symbolRotate: 180,
        itemStyle: { color: SENTIMENT_COLORS.bearish },
        label: {
          show: true,
          position: "top",
          formatter: (params: { name?: string }) => params.name ?? "",
          fontSize: 10,
          color: SENTIMENT_COLORS.bearish,
        },
        z: 10,
      } as EChartsOption["series"]);
    }

    if (neutralData.length > 0) {
      series.push({
        name: t("prediction.neutralPattern", "中性形态"),
        type: "scatter",
        coordinateSystem: "cartesian2d",
        data: neutralData.map((d) => ({
          value: [d[0], d[1]],
          name: d[2],
        })),
        symbol: "diamond",
        symbolSize: 12,
        itemStyle: { color: SENTIMENT_COLORS.neutral },
        label: {
          show: true,
          position: "top",
          formatter: (params: { name?: string }) => params.name ?? "",
          fontSize: 10,
          color: SENTIMENT_COLORS.neutral,
        },
        z: 10,
      } as EChartsOption["series"]);
    }

    return {
      backgroundColor: bgColor,
      animation: false,
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
          data: dates,
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
              color: theme === "dark" ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.1)",
            },
          },
        },
      ],
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: [0],
          start: Math.max(0, 100 - (80 / ohlcv.length) * 100),
          end: 100,
        },
        {
          show: true,
          xAxisIndex: [0],
          type: "slider",
          top: "82%",
          height: 30,
          start: Math.max(0, 100 - (80 / ohlcv.length) * 100),
          end: 100,
        },
      ],
      series,
    };
  }, [ohlcv, patterns, stockColors, theme, t]);

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

  useEffect(() => {
    if (chartInstance.current) {
      if (loading) {
        chartInstance.current.showLoading();
      } else {
        chartInstance.current.hideLoading();
      }
    }
  }, [loading]);

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={chartRef}
        className="w-full"
        style={{ height }}
      />
      {/* Pattern legend summary */}
      {patterns.length > 0 && (
        <div className="flex flex-wrap gap-2 px-2 pb-2">
          {patterns.slice(0, 10).map((p) => (
            <span
              key={`${p.date}-${p.name}`}
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
              style={{
                backgroundColor:
                  SENTIMENT_COLORS[p.sentiment as keyof typeof SENTIMENT_COLORS] + "20",
                color: SENTIMENT_COLORS[p.sentiment as keyof typeof SENTIMENT_COLORS],
                border: `1px solid ${SENTIMENT_COLORS[p.sentiment as keyof typeof SENTIMENT_COLORS]}40`,
              }}
            >
              <span>{p.date}</span>
              <span className="font-semibold">{p.label}</span>
              <span className="opacity-70">
                {(p.confidence * 100).toFixed(0)}%
              </span>
            </span>
          ))}
          {patterns.length > 10 && (
            <span className="text-xs text-muted-foreground self-center">
              +{patterns.length - 10} {t("prediction.morePatterns", "更多")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(PatternKlineChart);
