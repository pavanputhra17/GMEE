import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactElement } from 'react';
import { setSessionTokens, setSessionUser, type AccountUser } from '../src/lib/session';

export function renderWithClient(ui: ReactElement, options?: RenderOptions) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false, refetchOnReconnect: false }, mutations: { retry: false } },
  });
  return { ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>, options), client };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

export function mockApi(handler: (endpoint: string, init?: RequestInit) => Response | Promise<Response>) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? String(input) : input.url, 'http://localhost');
    return handler(url.pathname.replace(/^\/api\/v1/, '') + url.search, init);
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

export const accountFixture: AccountUser = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', email: 'reviewer@example.com',
  full_name: 'Corpus Reviewer', role: 'user', is_active: true, created_at: '2026-09-01T00:00:00Z',
};

export function signInFixture(overrides: Partial<AccountUser> = {}): void {
  setSessionTokens({ access_token: 'test-access', refresh_token: 'test-refresh', token_type: 'bearer' });
  setSessionUser({ ...accountFixture, ...overrides });
}

export const readyFixture = { status: 'ready', postgres: 'ok', neo4j: 'ok', redis: 'ok' };
export const zeroDashboard = {
  generated_at: '2026-10-03T10:00:00Z',
  services: { postgres: 'ok', neo4j: 'ok', redis: 'ok' },
  articles_total: 0, claims_total: 0, embedded_claims: 0, entities_total: 0,
  graph: { available: true, nodes: {}, relationships: 0 },
  cache: { available: true, used_memory_human: '0B', used_memory_mb: 0 },
};

export function emptyDashboardApi(endpoint: string): Response {
  if (endpoint === '/health/ready') return jsonResponse(readyFixture);
  if (endpoint === '/dashboard') return jsonResponse(zeroDashboard);
  if (endpoint === '/alerts') return jsonResponse({
    generated_at: zeroDashboard.generated_at, alerts: [],
    stats: { articles_24h: 0, articles_prior_24h: 0, disputed_24h: 0, disputed_prior_24h: 0, mutations_24h: 0, mutations_prior_24h: 0 },
  });
  if (endpoint.startsWith('/alerts/feed')) return jsonResponse({ generated_at: zeroDashboard.generated_at, items: [], counts: { unacknowledged: 0, by_severity: {}, by_kind: {} } });
  if (endpoint === '/corpus/stats') return jsonResponse({ total: 0, embedded: 0, domains: 0, earliest: null, latest: null, nlp_counts: { pending: 0 } });
  if (endpoint.startsWith('/corpus/graph/story-clusters')) return jsonResponse({ clusters: [] });
  if (endpoint.startsWith('/corpus/articles/recent')) return jsonResponse({ items: [] });
  if (endpoint.startsWith('/corpus/articles?')) return jsonResponse({ total: 0, items: [], domains: [], limit: 25, offset: 0 });
  if (endpoint === '/verdicts/stats') return jsonResponse({ total_claims: 0, distribution: [], outlets: [] });
  if (endpoint === '/verdicts/leaderboard') return jsonResponse({ ranking: [] });
  if (endpoint === '/verdicts' || endpoint.startsWith('/verdicts?')) return jsonResponse({ total: 0, items: [] });
  if (endpoint.startsWith('/graph/timeline')) return jsonResponse({ clusters: [], count: 0, focused: false });
  if (endpoint === '/graph/full' || endpoint === '/graph/claims') return jsonResponse({ nodes: [], edges: [], counts: { nodes: 0, edges: 0 } });
  if (endpoint.startsWith('/graph/scoops')) return jsonResponse({ races: [], count: 0 });
  if (endpoint.startsWith('/verdicts/game/mutations')) return jsonResponse({ chains: [] });
  return jsonResponse({ detail: 'No fixture for this API endpoint' }, 404);
}
