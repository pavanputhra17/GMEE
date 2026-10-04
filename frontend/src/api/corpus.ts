import { apiClient, type ApiRequestOptions } from './client';

export interface CorpusArticle {
  id: string;
  title: string;
  url: string;
  author: string | null;
  domain: string | null;
  language: string | null;
  published_at: string | null;
  word_count: number | null;
  nlp_status?: string;
  excerpt?: string;
}

export interface CorpusListResponse {
  total: number;
  limit: number;
  offset: number;
  items: CorpusArticle[];
  domains: Array<{ name: string; count: number }>;
}

export interface RecentArticle {
  id: string;
  title: string;
  url: string;
  domain: string | null;
  source_name: string | null;
  collected_at: string | null;
  published_at: string | null;
  word_count: number | null;
}

export interface StoryCluster {
  id: string;
  title: string;
  domain: string;
  url: string;
  deg: number;
  mass: number;
  neighbors: Array<{
    id: string;
    title: string;
    domain: string;
    url: string;
    score: number;
  }>;
}

export interface CorpusStats {
  total: number;
  embedded: number;
  domains: number;
  earliest: string | null;
  latest: string | null;
  nlp_counts: Record<string, number>;
}

export interface SearchResult {
  query: string;
  count: number;
  items: Array<{
    id: string; title: string; url: string; author: string | null;
    domain: string | null; published_at: string | null;
    word_count: number | null; score: number;
  }>;
}

export const corpusApi = {
  stats: (options?: ApiRequestOptions) => apiClient.get<CorpusStats>('/corpus/stats', options),

  search: (q: string, limit = 10, options?: ApiRequestOptions) =>
    apiClient.get<SearchResult>(`/corpus/search?q=${encodeURIComponent(q)}&limit=${limit}`, { timeoutMs: 45_000, ...options }),

  list: (params: { q?: string; domain?: string; limit?: number; offset?: number }, options?: ApiRequestOptions) => {
    const sp = new URLSearchParams();
    if (params.q) sp.set('q', params.q);
    if (params.domain) sp.set('domain', params.domain);
    sp.set('limit', String(params.limit ?? 30));
    sp.set('offset', String(params.offset ?? 0));
    return apiClient.get<CorpusListResponse>(`/corpus/articles?${sp.toString()}`, options);
  },

  recent: (limit = 12, options?: ApiRequestOptions) =>
    apiClient.get<{ items: RecentArticle[] }>(`/corpus/articles/recent?limit=${limit}`, options),

  storyClusters: (minLinks = 3, limit = 6, options?: ApiRequestOptions) =>
    apiClient.get<{ clusters: StoryCluster[] }>(`/corpus/graph/story-clusters?min_links=${minLinks}&limit=${limit}`, options),
};
