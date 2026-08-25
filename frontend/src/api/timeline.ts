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
  clusters: (limit = 60) =>
    apiClient.get(`/graph/timeline?limit=${limit}`) as Promise<{
      clusters: TimelineCluster[];
      count: number;
    }>,
};
