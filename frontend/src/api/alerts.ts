import { apiClient, type ApiRequestOptions } from './client';

export interface AlertSignal {
  type: string;
  severity: 'info' | 'warn' | 'critical';
  title: string;
  detail: string;
}

export interface AlertSnapshot {
  generated_at: string;
  alerts: AlertSignal[];
  stats: {
    articles_24h: number;
    articles_prior_24h: number;
    disputed_24h: number;
    disputed_prior_24h: number;
    mutations_24h: number;
    mutations_prior_24h: number;
  };
}

export interface FeedAlert {
  id: string;
  kind: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  body: string | null;
  claim_id: string | null;
  payload: Record<string, unknown> | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  acknowledged_at: string | null;
}

export interface AlertFeed {
  generated_at: string;
  items: FeedAlert[];
  counts: {
    unacknowledged: number;
    by_severity: Record<string, number>;
    by_kind: Record<string, number>;
  };
}

export const alertsApi = {
  snapshot: (options?: ApiRequestOptions) => apiClient.get<AlertSnapshot>('/alerts', options),

  feed: (limit = 12, options?: ApiRequestOptions) =>
    apiClient.get<AlertFeed>(`/alerts/feed?limit=${limit}`, options),
};
