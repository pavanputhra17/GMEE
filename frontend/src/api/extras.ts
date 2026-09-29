import { apiClient } from './client';

export interface ScoopRacer {
  id: string;
  title: string;
  domain: string | null;
  url: string | null;
  published: string;
  lag_seconds: number;
  position: number;
}

export interface ScoopRace {
  story: string;
  winner_domain: string | null;
  racers: ScoopRacer[];
  field_size: number;
  lag_spread_seconds: number;
}

export interface MutationVersion {
  id: string;
  text: string;
  domain: string | null;
  published_at: string | null;
  article_title?: string | null;
}

export interface MutationChain {
  chain_id: string;
  size: number;
  distinct_outlets: number;
  versions: MutationVersion[];
}

export interface GameClaim {
  id: string;
  text: string;
  domain: string | null;
  published_at: string | null;
}

export interface DiffSegment {
  type: 'same' | 'changed';
  old: string;
  new: string;
  kinds: string[];
}

export interface LineageDiff {
  from_index: number;
  to_index: number;
  from_id: string;
  to_id: string;
  similarity: number;
  mutation_types: string[];
  numeric_changes: Array<{ removed: string; added: string }>;
  entity_changes: Array<{ removed: string; added: string }>;
  hedge_changes: Array<{ word: string; direction: string }>;
  segments: DiffSegment[];
}

export interface MutationLineage {
  root: string;
  versions: MutationVersion[];
  edges: Array<{ from: string; to: string; score: number }>;
  diffs: LineageDiff[];
  counts: { versions: number; edges: number; component_claims: number };
}

export interface FeedbackResult {
  status: string;
  claim_id: string;
  vote: string;
}

export const extrasApi = {
  scoops: (limit = 10) =>
    apiClient.get(`/graph/scoops?limit=${limit}`) as Promise<{ races: ScoopRace[]; count: number }>,
  mutations: (limit = 6) =>
    apiClient.get(`/verdicts/game/mutations?min_versions=2&limit=${limit}`) as Promise<{
      chains: MutationChain[];
    }>,
  gameClaim: () => apiClient.get('/verdicts/game/claim') as Promise<GameClaim>,
  lineage: (claimId: string) =>
    apiClient.get(`/graph/lineage/${claimId}`) as Promise<MutationLineage>,
  feedback: (
    claimId: string,
    vote: 'AGREE' | 'DISAGREE',
    correctedVerdict?: string | null,
  ) =>
    apiClient.post('/verdicts/feedback', {
      claim_id: claimId,
      vote,
      corrected_verdict: correctedVerdict ?? null,
    }) as Promise<FeedbackResult>,
};
