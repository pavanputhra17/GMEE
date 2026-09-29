import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EarlyWarning } from '../src/components/EarlyWarning';

const feedPayload = {
  generated_at: '2026-09-20T10:00:00+00:00',
  items: [
    {
      id: 'alert-1',
      kind: 'CONTRADICTION',
      severity: 'CRITICAL',
      title: 'Cross-outlet contradiction detected (signal 0.42)',
      body: 'The raid killed 12 civilians.',
      claim_id: '11111111-1111-1111-1111-111111111111',
      payload: { contradiction: 0.42 },
      first_seen_at: '2026-09-20T09:30:00+00:00',
      last_seen_at: '2026-09-20T09:45:00+00:00',
      acknowledged_at: null,
    },
    {
      id: 'alert-2',
      kind: 'CORROBORATION',
      severity: 'INFO',
      title: 'Independently corroborated (80% corroboration signal)',
      body: 'Temperatures rose over the decade.',
      claim_id: null,
      payload: null,
      first_seen_at: '2026-09-20T08:00:00+00:00',
      last_seen_at: '2026-09-20T08:00:00+00:00',
      acknowledged_at: null,
    },
  ],
  counts: { unacknowledged: 2, by_severity: { CRITICAL: 1, INFO: 1 }, by_kind: {} },
};

const snapshotPayload = {
  generated_at: '2026-09-20T10:00:00+00:00',
  alerts: [
    {
      type: 'MUTATION_SURGE',
      severity: 'critical',
      title: 'Claim mutations accelerating',
      detail: '9 new EVOLVED_FROM links detected in the last 24h (previous 24h: 1).',
    },
  ],
  stats: {
    articles_24h: 42,
    articles_prior_24h: 7,
    disputed_24h: 0,
    disputed_prior_24h: 0,
    mutations_24h: 9,
    mutations_prior_24h: 1,
  },
};

vi.mock('../src/api/client', () => ({
  apiClient: {
    get: vi.fn(async (endpoint: string) => {
      if (endpoint.startsWith('/alerts/feed')) return feedPayload;
      if (endpoint.startsWith('/alerts')) return snapshotPayload;
      return {};
    }),
    post: vi.fn(async () => ({})),
  },
}));

const renderPanel = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EarlyWarning />
    </QueryClientProvider>,
  );
};

describe('<EarlyWarning/> — persisted alerts + 24h snapshot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders persisted alert rows with severity and kind labels', async () => {
    renderPanel();
    expect(await screen.findByText(/Cross-outlet contradiction detected/i)).toBeTruthy();
    expect(await screen.findByText(/Independently corroborated/i)).toBeTruthy();
    expect(screen.getByText('2 open')).toBeTruthy();
    expect(screen.getByText('1 critical')).toBeTruthy();
    expect(screen.getByText('cross-outlet contradiction')).toBeTruthy();
    expect(screen.getByText('independent corroboration')).toBeTruthy();
  });

  it('surfaces the stateless 24h spike snapshot alongside the feed', async () => {
    renderPanel();
    expect(await screen.findByText(/Claim mutations accelerating/i)).toBeTruthy();
    expect(screen.getByText(/Mutations · 24h/i)).toBeTruthy();
    expect(screen.getByText(/prev 1/)).toBeTruthy();
  });

  it('shows the quiet state when no alerts are open', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementation(async (endpoint: string) => {
      if (endpoint.startsWith('/alerts/feed')) {
        return {
          ...feedPayload,
          items: [],
          counts: { unacknowledged: 0, by_severity: {}, by_kind: {} },
        };
      }
      return {
        ...snapshotPayload,
        alerts: [
          {
            type: 'QUIET',
            severity: 'info',
            title: 'All quiet',
            detail: 'No anomalous activity.',
          },
        ],
      };
    });
    renderPanel();
    expect(await screen.findByText(/All quiet — no anomalous collection/i)).toBeTruthy();
  });

  it('never fabricates rows when the backend is unreachable', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementation(async () => {
      throw new TypeError('Failed to fetch');
    });
    renderPanel();
    expect(await screen.findByText(/Alert engine unreachable/i)).toBeTruthy();
    expect(screen.queryByText(/Cross-outlet contradiction detected/i)).toBeNull();
  });
});
