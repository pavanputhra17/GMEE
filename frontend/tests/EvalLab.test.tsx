import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EvalLab } from '../src/components/EvalLab';
import { evalApi } from '../src/api/eval';

vi.mock('../src/api/eval', () => ({
  evalApi: {
    loadAnnotator: vi.fn(() => ''),
    saveAnnotator: vi.fn(),
    next: vi.fn(),
    label: vi.fn(),
    progress: vi.fn(),
  },
}));

const evalMock = vi.mocked(evalApi, true);

const pairPayload = {
  done: false,
  pair: {
    pair_id: '11111111-1111-1111-1111-111111111111',
    a: { text: 'Claim A text here', domain: 'a.example' },
    b: { text: 'Claim B text here', domain: 'b.example' },
  },
};

const progressPayload = {
  total_pairs: 761,
  labeled_votes: 11,
  labeled_pairs_distinct: 8,
  by_bucket: [
    { bucket: 'b00', pairs: 300, labeled: 3 },
    { bucket: 'b95', pairs: 6, labeled: 1 },
  ],
  per_annotator: {},
  inter_annotator: [],
  complete: false,
};

const renderLab = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EvalLab />
    </QueryClientProvider>,
  );
};
describe('<EvalLab/> — gold-standard labeling workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    evalMock.loadAnnotator.mockReturnValue('');
    evalMock.progress.mockResolvedValue({ ...progressPayload });
    evalMock.next.mockResolvedValue({ ...pairPayload });
    evalMock.label.mockResolvedValue({
      status: 'recorded',
      pair_id: pairPayload.pair.pair_id,
      label: 'DISTINCT',
    });
  });

  it('asks for an annotator handle before pulling pairs', () => {
    renderLab();
    expect(screen.getByText(/Enter an annotator handle/i)).toBeTruthy();
    expect(evalMock.next).not.toHaveBeenCalled();
  });

  it('serves a blinded pair — texts and outlets only, no score cues', async () => {
    evalMock.loadAnnotator.mockReturnValue('tester');
    renderLab();
    expect(await screen.findByText(/Claim A text here/)).toBeTruthy();
    expect(await screen.findByText(/Claim B text here/)).toBeTruthy();
    expect(await screen.findByText('a.example')).toBeTruthy();
    // the blind holds: the served pair carries no score, bucket or verdict —
    // note this asserts the PAYLOAD shape (not the page text, which carries
    // an explanatory "similarity scores are withheld" note by design)
    const served = evalMock.next.mock.results[0]?.value as unknown as Promise<{
      pair: { pair_id: string; a: Record<string, unknown>; b: Record<string, unknown> };
    }>;
    const payload = await served;
    expect(Object.keys(payload.pair).sort()).toEqual(['a', 'b', 'pair_id']);
    expect(Object.keys(payload.pair.a).sort()).toEqual(['domain', 'text']);
    expect(Object.keys(payload.pair.b).sort()).toEqual(['domain', 'text']);
    // and neither claim text looks like a leaked similarity score
    const claimTexts = `${String(payload.pair.a.text)} ${String(payload.pair.b.text)}`;
    expect(claimTexts).not.toMatch(/\b[01]\.\d{2}\b/);
  });

  it('records a vote and advances to the next pair', async () => {
    evalMock.loadAnnotator.mockReturnValue('tester');
    renderLab();
    await screen.findByText(/Claim A text here/);
    fireEvent.click(screen.getByText('Distinct'));
    await waitFor(() =>
      expect(evalMock.label).toHaveBeenCalledWith(
        '11111111-1111-1111-1111-111111111111',
        'tester',
        'DISTINCT',
      ),
    );
  });

  it('never fabricates pairs when the backend is unreachable', async () => {
    evalMock.loadAnnotator.mockReturnValue('tester');
    evalMock.next.mockRejectedValue(new TypeError('Failed to fetch'));
    renderLab();
    expect(await screen.findByText(/Eval backend unreachable/i)).toBeTruthy();
    expect(screen.queryByText(/Claim A text here/)).toBeNull();
  });

  it('shows coverage progress per bucket', async () => {
    evalMock.loadAnnotator.mockReturnValue('tester');
    renderLab();
    expect(await screen.findByText(/Coverage by similarity bucket/i)).toBeTruthy();
    expect(screen.getByText('b00')).toBeTruthy();
    expect(screen.getByText(/8 \/ 761 labeled/)).toBeTruthy();
  });
});

