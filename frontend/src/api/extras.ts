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

export const extrasApi = {
  scoops: (limit = 10) =>
    apiClient.get(`/graph/scoops?limit=${limit}`) as Promise<{ races: ScoopRace[]; count: number }>,
  mutations: (limit = 6) =>
    apiClient.get(`/verdicts/game/mutations?min_versions=2&limit=${limit}`) as Promise<{
      chains: MutationChain[];
    }>,
  gameClaim: () => apiClient.get('/verdicts/game/claim') as Promise<GameClaim>,
};
