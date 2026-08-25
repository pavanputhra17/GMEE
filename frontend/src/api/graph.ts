import { apiClient } from './client';

export interface GraphNode {
  id: string;
  title: string;
  domain: string | null;
  url: string | null;
  published_at?: string | null;
  deg: number;
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
  full: () => apiClient.get('/graph/full') as Promise<FullGraph>,
  claims: () => apiClient.get('/graph/claims') as Promise<FullGraph & { nodes: ClaimGraphNode[] }>,
};
