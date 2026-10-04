import { apiClient, type ApiRequestOptions } from './client';

export interface GraphNode {
  id: string;
  title: string;
  domain: string | null;
  url?: string | null;
  article_id?: string | null;
  published_at?: string | null;
  deg?: number;
  verdict?: string;
  prob?: number | null;
}

export interface GraphEdge {
  src: string;
  dst: string;
  score: number;
}

export interface FullGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  counts: { nodes: number; edges: number };
}

export interface ClaimGraphNode {
  id: string;
  title: string;
  domain: string | null;
  verdict?: string;
  prob?: number | null;
}

export const graphApi = {
  full: (options?: ApiRequestOptions) => apiClient.get<FullGraph>('/graph/full', options),
  claims: (options?: ApiRequestOptions) => apiClient.get<FullGraph>('/graph/claims', options),
};
