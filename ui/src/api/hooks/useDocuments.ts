import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post } from "../client";
import type {
  AnalysisStatus,
  DocumentDetail,
  DocumentSummary,
  RiskReport,
} from "../../types/api";

export const docKeys = {
  all: ["docs"] as const,
  detail: (id: string) => ["docs", id] as const,
  analysis: (id: string) => ["docs", id, "analysis"] as const,
  risk: (id: string) => ["docs", id, "risk"] as const,
};

export function useDocumentList() {
  return useQuery({
    queryKey: docKeys.all,
    queryFn: () => get<DocumentSummary[]>("/docs"),
  });
}

export function useDocument(id: string | null) {
  return useQuery({
    queryKey: docKeys.detail(id ?? ""),
    queryFn: () => get<DocumentDetail>(`/docs/${id}`),
    enabled: !!id,
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: FormData) =>
      post<DocumentSummary>("/docs/upload", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.all }),
  });
}

export function useTriggerAnalysis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ docId, jurisdiction }: { docId: string; jurisdiction?: string }) =>
      post<AnalysisStatus>(`/docs/${docId}/analyze`, { jurisdiction }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: docKeys.analysis(vars.docId) });
    },
  });
}

export function useAnalysisStatus(docId: string | null) {
  return useQuery({
    queryKey: docKeys.analysis(docId ?? ""),
    queryFn: () => get<AnalysisStatus>(`/docs/${docId}/analysis`),
    enabled: !!docId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 2000 : false;
    },
  });
}

export function useRiskReport(docId: string | null) {
  return useQuery({
    queryKey: docKeys.risk(docId ?? ""),
    queryFn: () => get<RiskReport>(`/docs/${docId}/risk-report`),
    enabled: !!docId,
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => del(`/docs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: docKeys.all }),
  });
}
