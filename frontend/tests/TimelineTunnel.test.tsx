import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TimelineTunnel from '../src/components/TimelineTunnel';
import { timelineApi, TimelineCluster } from '../src/api/timeline';
import { useSelectedArticle, clearSelectedArticle } from '../src/lib/useSelectedArticle';

vi.mock('../src/api/timeline', () => ({
  timelineApi: { clusters: vi.fn() },
}));

vi.mock('../src/lib/useSelectedArticle', () => ({
  useSelectedArticle: vi.fn(),
  clearSelectedArticle: vi.fn(),
}));

const timelineMock = vi.mocked(timelineApi.clusters);
const selMock = vi.mocked(useSelectedArticle);
const clearMock = vi.mocked(clearSelectedArticle);


const FOCUS = { id: '11111111-1111-1111-1111-111111111111', title: 'Border Raid Focused Story', domain: 'www.thehindu.com' };

const mkCluster = (id: string, title: string, publishedAt: string): TimelineCluster => ({
  id,
  title,
  domain: 'www.thehindu.com',
  url: null,
  published_at: publishedAt,
  newest_member_at: publishedAt,
  deg: 3,
  members: [],
});

// Deliberately out of order — the tunnel must sort newest-first regardless
// of what the backend returns (index 0 = latest development).
const focusedPayload = {
  clusters: [
    mkCluster('p-oldest', 'First report: raid begins', '2026-09-01T08:00:00Z'),
    mkCluster('p-newest', 'Latest: ceasefire agreed', '2026-09-19T08:00:00Z'),
    mkCluster('p-mid', 'Middle: tanks mobilised', '2026-09-10T08:00:00Z'),
  ],
  count: 3,
  focused: true,
};

const renderTunnel = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TimelineTunnel />
    </QueryClientProvider>,
  );
};

describe('<TimelineTunnel/> — graph → focused story drill-down', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    timelineMock.mockResolvedValue({ ...focusedPayload });
  });

  afterEach(() => {
    cleanup();
  });

  it('with a selected story, fetches ONLY that story (article_id) and shows the focus chip', async () => {
    selMock.mockReturnValue(FOCUS);
    renderTunnel();
    expect(timelineMock).toHaveBeenCalledWith(60, FOCUS.id, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(await screen.findByText(/Border Raid Focused Story/)).toBeTruthy();
    expect(screen.getByText('All stories')).toBeTruthy();
    expect(screen.getByText(/ends at the earliest linked coverage returned/i)).toBeTruthy();
  });

  it("All stories clears the selection and returns to the generic tunnel", async () => {
    selMock.mockReturnValue(FOCUS);
    renderTunnel();
    fireEvent.click(await screen.findByText('All stories'));
    expect(clearMock).toHaveBeenCalledTimes(1);
  });

  it('without a selection, fetches the global timeline with no article_id filter', async () => {
    selMock.mockReturnValue(null);
    renderTunnel();
    expect(timelineMock).toHaveBeenCalledWith(60, undefined, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    await screen.findByText(/3 clusters · newest on top/i);
    expect(screen.queryByText('All stories')).toBeNull();
  });

  it('orders rings newest-first so diving deeper reads back to the first report', async () => {
    selMock.mockReturnValue(null);
    renderTunnel();
    // rail items render in dive order — newest must come before oldest
    await screen.findByText(/ceasefire agreed/i);
    const latest = screen.getByText(/Latest: ceasefire agreed/i);
    const first = screen.getByText(/First report: raid begins/i);
    expect(
      latest.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('focused empty state offers a way back instead of a blank tunnel', async () => {
    selMock.mockReturnValue(FOCUS);
    timelineMock.mockResolvedValue({ clusters: [], count: 0, focused: true });
    renderTunnel();
    expect(await screen.findByText(/No linked coverage found for this story/i)).toBeTruthy();
    fireEvent.click(screen.getByText(/Back to all stories/i));
    expect(clearMock).toHaveBeenCalledTimes(1);
  });
});
