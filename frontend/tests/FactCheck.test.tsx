import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FactCheck } from '../src/components/FactCheck';

const verdictRow = {
  id: '11111111-1111-1111-1111-111111111111',
  claim_text: 'Global average temperature rose in the last decade.',
  verdict: 'SUPPORTED',
  probability: 0.81,
  extraction_confidence: 0.93,
  outlet: 'example-news.com',
  article_title: 'Climate study published',
  article_url: 'https://example-news.com/article',
};

const verdictDetail = {
  ...verdictRow,
  verdict_rationale: 'P(supported)=0.81 [SUPPORTED]. Strongest factors: corroboration raises confidence (0.90).',
  verdict_evidence: {},
};

vi.mock('../src/api/client', () => ({
  apiClient: {
    get: vi.fn(async (endpoint: string) => {
      if (endpoint.includes('/leaderboard')) {
        return { ranking: [{ name: 'example-news.com', claims_total: 5 }] };
      }
      if (endpoint.includes('/game')) {
        return { id: 'g1', text: 'X', domain: 'd', published_at: null };
      }
      if (endpoint.includes('/stats')) {
        return { total_claims: 10, distribution: [], outlets: [] };
      }
      if (endpoint.includes('11111111')) return verdictDetail;
      // /verdicts list endpoint
      return { total: 1, items: [verdictRow] };
    }),
    post: vi.fn(async () => ({ status: 'recorded', claim_id: 'x', vote: 'AGREE' })),
  },
}));

const renderFactCheck = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FactCheck />
    </QueryClientProvider>,
  );
};

describe('<FactCheck/> — Verdict Engine surface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a SUPPORTED verdict with its probability and outlet', async () => {
    renderFactCheck();
    const claim = await screen.findByText(/Global average temperature rose/i);
    expect(claim).toBeTruthy();
    // Band chip label for SUPPORTED appears once evidence loads
    const chips = await screen.findAllByText(/SUPPORTED/);
    expect(chips.length).toBeGreaterThan(0);
    // Probability rendered as a percentage ("81.0%")
    expect(screen.getAllByText(/81\.0%/).length).toBeGreaterThan(0);
    // Outlet attribution is displayed (source transparency requirement)
    const outlets = await screen.findAllByText(/example-news\.com/);
    expect(outlets.length).toBeGreaterThan(0);
  });

  it('shows an empty-state message when no verdicted claims exist yet', async () => {
    const { apiClient } = await import('../src/api/client');
    (apiClient.get as ReturnType<typeof vi.fn>).mockImplementationOnce(async () => ({ total: 0, items: [] }));
    renderFactCheck();
    expect(await screen.findByText(/No verdicts yet/i)).toBeTruthy();
  });

  it('records human feedback from the evidence drawer', async () => {
    renderFactCheck();
    fireEvent.click(await screen.findByText(/Global average temperature rose/i));
    const agree = await screen.findByRole('button', { name: /^AGREE$/i });
    fireEvent.click(agree);
    expect(await screen.findByText(/Vote recorded/i)).toBeTruthy();
    const { apiClient } = await import('../src/api/client');
    expect(apiClient.post).toHaveBeenCalledWith('/verdicts/feedback', {
      claim_id: '11111111-1111-1111-1111-111111111111',
      vote: 'AGREE',
      corrected_verdict: null,
    });
  });
});
