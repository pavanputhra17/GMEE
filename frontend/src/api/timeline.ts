import { apiClient } from './client';

export interface TimelineMember {
  id: string;
  title: string;
  domain: string | null;
  url: string | null;
  published_at: string | null;
  score: number;
}

export interface TimelineCluster {
  id: string;
  title: string;
  domain: string | null;
  url: string | null;
  published_at: string | null;
  newest_member_at: string | null;
  deg: number;
  members: TimelineMember[];
}

export const timelineApi = {
  clusters: (limit = 60, articleId?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (articleId) params.set('article_id', articleId);
    return apiClient.get(`/graph/timeline?${params.toString()}`) as Promise<{
      clusters: TimelineCluster[];
      count: number;
      /** true when the response is scoped to one story (article_id drill-down) */
      focused: boolean;
    }>;
  },
};
