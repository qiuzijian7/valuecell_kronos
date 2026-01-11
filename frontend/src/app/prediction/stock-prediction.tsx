import BackButton from "@valuecell/button/back-button";
import { useTheme } from "next-themes";
import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { useGetStockDetail } from "@/api/stock";
import { useKronosPrediction } from "@/api/kronos";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import PredictionChart from "./components/prediction-chart";
import type { Route } from "./+types/stock-prediction";

function StockPrediction() {
  const { t, i18n } = useTranslation();
  const { resolvedTheme } = useTheme();
  const { stockId } = useParams<Route.LoaderArgs["params"]>();
  const ticker = stockId || "";

  const [predictionParams, setPredictionParams] = useState({
    lookback: 400,
    pred_len: 120,
    temperature: 1.0,
    top_p: 0.9,
  });

  // Fetch stock detail data
  const {
    data: stockDetailData,
    isLoading: isDetailLoading,
    error: detailError,
  } = useGetStockDetail({ ticker });

  // Kronos prediction
  const {
    data: predictionData,
    isLoading: isPredicting,
    error: predictionError,
    refetch: runPrediction,
  } = useKronosPrediction({
    ticker,
    ...predictionParams,
  });

  const handlePredict = () => {
    runPrediction();
  };

  // Handle loading states
  if (isDetailLoading) {
    return (
      <div className="flex h-full flex-col gap-8 bg-card px-8 py-6">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-[420px] w-full" />
      </div>
    );
  }

  // Handle error states
  if (detailError) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-lg text-red-500">
          {t("home.stock.error", { message: detailError?.message })}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-6 bg-card px-8 py-6">
      <div className="flex flex-col gap-4">
        <BackButton />
        <div className="flex items-center gap-4">
          <span className="font-bold text-foreground text-lg">
            {stockDetailData?.display_name ?? ticker}
          </span>
          <span className="text-muted-foreground text-sm">
            {t("prediction.kronosAnalysis")}
          </span>
        </div>
      </div>

      {/* Prediction Controls */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-muted/50 p-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">
            {t("prediction.lookback")}:
          </label>
          <select
            value={predictionParams.lookback}
            onChange={(e) =>
              setPredictionParams((p) => ({
                ...p,
                lookback: Number(e.target.value),
              }))
            }
            className="rounded border border-border bg-background px-2 py-1 text-sm"
          >
            <option value={200}>200</option>
            <option value={400}>400</option>
            <option value={512}>512</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">
            {t("prediction.predLen")}:
          </label>
          <select
            value={predictionParams.pred_len}
            onChange={(e) =>
              setPredictionParams((p) => ({
                ...p,
                pred_len: Number(e.target.value),
              }))
            }
            className="rounded border border-border bg-background px-2 py-1 text-sm"
          >
            <option value={60}>60</option>
            <option value={120}>120</option>
            <option value={180}>180</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm text-muted-foreground">
            {t("prediction.temperature")}:
          </label>
          <input
            type="number"
            step="0.1"
            min="0.1"
            max="2.0"
            value={predictionParams.temperature}
            onChange={(e) =>
              setPredictionParams((p) => ({
                ...p,
                temperature: Number(e.target.value),
              }))
            }
            className="w-16 rounded border border-border bg-background px-2 py-1 text-sm"
          />
        </div>

        <Button
          onClick={handlePredict}
          disabled={isPredicting}
          className="ml-auto"
        >
          {isPredicting ? t("prediction.predicting") : t("prediction.startPrediction")}
        </Button>
      </div>

      {/* Prediction Error */}
      {predictionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          {t("prediction.error", { message: predictionError.message })}
        </div>
      )}

      {/* Prediction Failed (API returned success=false) */}
      {predictionData && !predictionData.success && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 p-4 text-orange-600 dark:border-orange-800 dark:bg-orange-900/20 dark:text-orange-400">
          <div className="font-semibold mb-1">{t("prediction.predictionFailed")}</div>
          <div>{predictionData.message}</div>
        </div>
      )}

      {/* Prediction Chart */}
      <div className="flex-1">
        {isPredicting ? (
          <div className="flex h-[420px] items-center justify-center">
            <div className="text-center">
              <div className="mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto" />
              <p className="text-muted-foreground">{t("prediction.analyzing")}</p>
            </div>
          </div>
        ) : predictionData ? (
          <PredictionChart
            predictionData={predictionData}
            ticker={ticker}
            theme={resolvedTheme === "dark" ? "dark" : "light"}
            locale={i18n.language}
          />
        ) : (
          <div className="flex h-[420px] items-center justify-center rounded-lg border border-dashed border-border">
            <div className="text-center">
              <p className="mb-2 text-lg font-medium text-foreground">
                {t("prediction.noData")}
              </p>
              <p className="text-muted-foreground">
                {t("prediction.clickToStart")}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Prediction Results Summary */}
      {predictionData && (
        <div className={`rounded-lg border p-4 ${
          predictionData.success 
            ? "border-border bg-muted/50" 
            : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20"
        }`}>
          <h3 className="mb-3 font-semibold text-foreground">
            {t("prediction.resultSummary")}
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div>
              <span className="text-muted-foreground">{t("prediction.predictionType")}:</span>
              <span className={`ml-2 font-medium ${!predictionData.success ? "text-red-600 dark:text-red-400" : ""}`}>
                {predictionData.prediction_type}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">{t("prediction.dataPoints")}:</span>
              <span className="ml-2 font-medium">{predictionData.prediction_results?.length ?? 0}</span>
            </div>
            {!predictionData.success && (
              <div className="col-span-2">
                <span className="text-muted-foreground">{t("prediction.errorMessage")}:</span>
                <span className="ml-2 font-medium text-red-600 dark:text-red-400">
                  {predictionData.message}
                </span>
              </div>
            )}
            {predictionData.success && predictionData.time_range && (
              <>
                <div>
                  <span className="text-muted-foreground">{t("prediction.inputRange")}:</span>
                  <span className="ml-2 font-medium text-xs">
                    {predictionData.time_range.input_start} ~ {predictionData.time_range.input_end}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">{t("prediction.predRange")}:</span>
                  <span className="ml-2 font-medium text-xs">
                    {predictionData.time_range.pred_start} ~ {predictionData.time_range.pred_end}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(StockPrediction);
