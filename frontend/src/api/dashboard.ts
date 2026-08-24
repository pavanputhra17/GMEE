import { apiClient } from './client';

export interface DashboardSnapshot {
  generated_at: string;
  services: { postgres: string; neo4j: string; redis: string };
  articles_total?: number;
  nlp_status_counts?: Record<string, number>;
  claims_total?: number;
  embedded_claims?: number;
  entities_total?: number;
  last_evolution_run?: { run_at: string; claims_in_corpus: number } | null;
  corpus?: unknown;
  graph?: {
    available: boolean;
    nodes: Record<string, number>;
    relationships: number;
  } | null;
  cache?: {
    available: boolean;
    used_memory_human: string;
    used_memory_mb: number;
  } | null;
}

export const fetchDashboard = (): Promise<DashboardSnapshot> =>
  apiClient.get('/dashboard');
