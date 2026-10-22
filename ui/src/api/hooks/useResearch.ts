import { useQuery } from "@tanstack/react-query";
import { get } from "../client";
import type { ArticleDetail, CitationNetwork, GraphData, SearchResult } from "../../types/api";

export function useArticle(
  jurisdiction: string | null,
  code: string | null,
  articleId: string | null,
) {
  return useQuery({
    queryKey: ["articles", jurisdiction, code, articleId],
    queryFn: () =>
      get<ArticleDetail>(`/articles/${jurisdiction}/${code}/${articleId}`),
    enabled: !!(jurisdiction && code && articleId),
  });
}

export function useArticleCitations(
  jurisdiction: string | null,
  code: string | null,
  articleId: string | null,
) {
  return useQuery({
    queryKey: ["articles", jurisdiction, code, articleId, "citations"],
    queryFn: () =>
      get<CitationNetwork>(
        `/articles/${jurisdiction}/${code}/${articleId}/citations`,
      ),
    enabled: !!(jurisdiction && code && articleId),
  });
}

export interface ArticleSuggestion {
  id: string;
  heading: string;
  code: string;
}

export function useArticleAutocomplete(q: string) {
  return useQuery({
    queryKey: ["articles-autocomplete", q],
    queryFn: () => get<ArticleSuggestion[]>(`/articles/autocomplete?q=${encodeURIComponent(q)}&limit=20`),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
}

interface BackendSearchResponse {
  query: string;
  total: number;
  results: Array<{
    text: string;
    score: number;
    source_type: string;
    jurisdiction: string;
    article_id: string | null;
    case_id: string | null;
    tags: string[];
  }>;
}

export function useSearch(
  query: string,
  jurisdiction?: string,
  sourceType?: string,
) {
  const params = new URLSearchParams({ q: query });
  if (jurisdiction) params.set("jurisdiction", jurisdiction);
  if (sourceType) params.set("source_type", sourceType);
  return useQuery({
    queryKey: ["search", query, jurisdiction, sourceType],
    queryFn: async (): Promise<SearchResult[]> => {
      const resp = await get<BackendSearchResponse>(`/search?${params.toString()}`);
      return resp.results.map((r, i) => ({
        chunk_id: r.article_id ?? r.case_id ?? String(i),
        source_type: r.source_type,
        article_id: r.article_id,
        case_id: r.case_id,
        jurisdiction: r.jurisdiction,
        content: r.text,
        score: r.score,
        tags: r.tags,
      }));
    },
    enabled: query.length > 2,
    staleTime: 30_000,
  });
}

export function useCorpusGraph(corpusId: string | null) {
  return useQuery({
    queryKey: ["graph", corpusId],
    queryFn: () => get<GraphData>(`/corpus/${corpusId}/graph`),
    enabled: !!corpusId,
    staleTime: 60_000,
  });
}

export function useGlobalGraph() {
  return useQuery({
    queryKey: ["graph", "global"],
    queryFn: () => get<GraphData>("/graph"),
    staleTime: 5 * 60_000,
  });
}
