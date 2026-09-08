import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CorpusExplorer from '../src/components/CorpusExplorer';

const article = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  title: 'Disinformation network mapped across three outlets',
  url: 'https://x.com/a1',
  author: null,
  domain: 'x.com',
  language: 'en',
  published_at: '2026-01-02T00:00:00Z',
  word_count: 320,
};

vi.mock('../src/api/corpus', () => ({
  corpusApi: {
    list: vi.fn(async () => ({
      total: 1,
      limit: 25,
      offset: 0,
      items: [article],
      domains: [{ name: 'x.com', count: 1 }],
    })),
    storyClusters: vi.fn(async () => ({ clusters: [] })),
    recent: vi.fn(async () => ({ items: [] })),
  },
}));

const renderExplorer = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CorpusExplorer />
    </QueryClientProvider>,
  );
};

describe('<CorpusExplorer/> — real corpus listing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists articles from the corpus API with their domain', async () => {
    renderExplorer();
    expect(await screen.findByText(/Disinformation network mapped/i)).toBeTruthy();
    expect(await screen.findByText('Story Clusters')).toBeTruthy();
    expect(await screen.findAllByText(/x\.com/).then(a => a.length)).toBeGreaterThan(0);
  });

  it('passes search terms into the list query after submitting', async () => {
    const { corpusApi } = await import('../src/api/corpus');
    renderExplorer();
    await screen.findByText(/Disinformation network mapped/i);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'mutation' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() =>
      expect(corpusApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'mutation', offset: 0 }),
      ),
    );
  });
});
