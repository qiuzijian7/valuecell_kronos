import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ApiResponse, apiClient } from "@/lib/api-client";
import type {
  BacktestRequest,
  BacktestResultData,
  CreatePythonStrategy,
  PythonStrategy,
  UpdatePythonStrategy,
} from "@/types/python-strategy";

const QUERY_KEYS = {
  list: ["python-strategy", "list"],
  detail: (id: string) => ["python-strategy", "detail", id],
  template: ["python-strategy", "template"],
} as const;

export const useGetPythonStrategies = () => {
  return useQuery({
    queryKey: QUERY_KEYS.list,
    queryFn: () =>
      apiClient.get<ApiResponse<PythonStrategy[]>>("/python-strategies/"),
    select: (data) => data.data,
  });
};

export const useGetPythonStrategy = (id: string | undefined) => {
  return useQuery({
    queryKey: QUERY_KEYS.detail(id ?? ""),
    queryFn: () =>
      apiClient.get<ApiResponse<PythonStrategy>>(`/python-strategies/${id}`),
    select: (data) => data.data,
    enabled: !!id,
  });
};

export const useGetDefaultTemplate = () => {
  return useQuery({
    queryKey: QUERY_KEYS.template,
    queryFn: () =>
      apiClient.get<ApiResponse<{ code: string }>>(
        "/python-strategies/template/default",
      ),
    select: (data) => data.data.code,
  });
};

export const useCreatePythonStrategy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreatePythonStrategy) =>
      apiClient.post<ApiResponse<PythonStrategy>>("/python-strategies/", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.list });
    },
  });
};

export const useUpdatePythonStrategy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdatePythonStrategy }) =>
      apiClient.put<ApiResponse<PythonStrategy>>(
        `/python-strategies/${id}`,
        data,
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.list });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.detail(vars.id) });
    },
  });
};

export const useDeletePythonStrategy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.delete<ApiResponse<null>>(`/python-strategies/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.list });
    },
  });
};

export const useRunBacktest = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BacktestRequest) =>
      apiClient.post<ApiResponse<BacktestResultData>>(
        "/python-strategies/backtest",
        data,
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.list });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.detail(vars.strategy_id) });
    },
  });
};
