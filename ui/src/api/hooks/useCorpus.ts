import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { del, get, post } from "../client";
import type { CorpusIngestResponse, CorpusSummary, CorpusStats, SessionSummary, StoredMessage } from "../../types/api";

export const corpusKeys = {
  all: ["corpus"] as const,
  detail: (id: string) => ["corpus", id] as const,
  stats: (id: string) => ["corpus", id, "stats"] as const,
  sessions: (id: string) => ["corpus", id, "sessions"] as const,
};

export function useCorpusList() {
  return useQuery({
    queryKey: corpusKeys.all,
    queryFn: () => get<CorpusSummary[]>("/corpus"),
  });
}

export function useCorpusStats(corpusId: string | null) {
  return useQuery({
    queryKey: corpusKeys.stats(corpusId ?? ""),
    queryFn: () => get<CorpusStats>(`/corpus/${corpusId}/stats`),
    enabled: !!corpusId,
  });
}

export function useIngestCorpus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: FormData) =>
      post<CorpusIngestResponse>("/corpus", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: corpusKeys.all }),
  });
}

export function useDeleteCorpus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => del(`/corpus/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: corpusKeys.all }),
  });
}

export function useCorpusSessions(corpusId: string | null) {
  return useQuery({
    queryKey: corpusKeys.sessions(corpusId ?? ""),
    queryFn: () => get<SessionSummary[]>(`/corpus/${corpusId}/sessions`),
    enabled: !!corpusId,
  });
}

export function useCreateSession(corpusId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      post<SessionSummary>(`/corpus/${corpusId}/sessions`, { title }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: corpusKeys.sessions(corpusId) }),
  });
}

export function useDeleteSession(corpusId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      del(`/corpus/${corpusId}/sessions/${sessionId}`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: corpusKeys.sessions(corpusId) }),
  });
}

export function useSessionMessages(corpusId: string | null, sessionId: string | null) {
  return useQuery({
    queryKey: ["session-messages", corpusId, sessionId],
    queryFn: () =>
      get<StoredMessage[]>(`/corpus/${corpusId}/sessions/${sessionId}/messages`),
    enabled: !!(corpusId && sessionId),
    staleTime: Infinity,
  });
}

// ── Global (corpus-free) sessions ─────────────────────────────────────────────

interface GlobalSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export const globalSessionKeys = {
  all: ["global-sessions"] as const,
  messages: (id: string) => ["global-session-messages", id] as const,
};

export function useGlobalSessions() {
  return useQuery({
    queryKey: globalSessionKeys.all,
    queryFn: () => get<GlobalSession[]>("/sessions"),
  });
}

export function useCreateGlobalSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      post<GlobalSession>("/sessions", { title: title ?? "" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: globalSessionKeys.all }),
  });
}

export function useDeleteGlobalSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => del(`/sessions/${sessionId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: globalSessionKeys.all }),
  });
}

export function useGlobalSessionMessages(sessionId: string | null) {
  return useQuery({
    queryKey: globalSessionKeys.messages(sessionId ?? ""),
    queryFn: () => get<StoredMessage[]>(`/sessions/${sessionId}/messages`),
    enabled: !!sessionId,
    staleTime: Infinity,
  });
}
