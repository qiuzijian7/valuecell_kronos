import { useQuery } from "@tanstack/react-query";
import { type ApiResponse, apiClient } from "@/lib/api-client";

export interface KronosPredictionParams {
  ticker: string;
  lookback?: number;
  pred_len?: number;
  temperature?: number;
  top_p?: number;
  sample_count?: number;
}

export interface PredictionResult {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
}

export interface KronosPredictionResult {
  success: boolean;
  prediction_type: string;
  chart: string;
  prediction_results: PredictionResult[];
  actual_data: PredictionResult[];
  has_comparison: boolean;
  time_range?: {
    input_start: string;
    input_end: string;
    pred_start: string;
    pred_end: string;
  };
  message: string;
}

export const KRONOS_QUERY_KEYS = {
  prediction: (params: string[]) => ["kronos", "prediction", ...params],
  modelStatus: ["kronos", "model-status"],
  availableModels: ["kronos", "available-models"],
} as const;

export const useKronosPrediction = (params: KronosPredictionParams) => {
  return useQuery({
    queryKey: KRONOS_QUERY_KEYS.prediction([
      params.ticker,
      String(params.lookback ?? 400),
      String(params.pred_len ?? 120),
    ]),
    queryFn: () =>
      apiClient.post<ApiResponse<KronosPredictionResult>>("kronos/predict", {
        ticker: params.ticker,
        lookback: params.lookback ?? 400,
        pred_len: params.pred_len ?? 120,
        temperature: params.temperature ?? 1.0,
        top_p: params.top_p ?? 0.9,
        sample_count: params.sample_count ?? 1,
      }),
    select: (data) => data.data,
    enabled: false, // Manual trigger only
    retry: false,
  });
};

export interface KronosModelStatus {
  available: boolean;
  loaded: boolean;
  message: string;
  current_model?: {
    name: string;
    device: string;
  };
}

export const useKronosModelStatus = () => {
  return useQuery({
    queryKey: KRONOS_QUERY_KEYS.modelStatus,
    queryFn: () =>
      apiClient.get<ApiResponse<KronosModelStatus>>("kronos/model-status"),
    select: (data) => data.data,
  });
};

export interface KronosModelInfo {
  name: string;
  model_id: string;
  tokenizer_id: string;
  context_length: number;
  params: string;
  description: string;
}

export interface KronosAvailableModels {
  models: Record<string, KronosModelInfo>;
  model_available: boolean;
}

export const useKronosAvailableModels = () => {
  return useQuery({
    queryKey: KRONOS_QUERY_KEYS.availableModels,
    queryFn: () =>
      apiClient.get<ApiResponse<KronosAvailableModels>>("kronos/available-models"),
    select: (data) => data.data,
  });
};
