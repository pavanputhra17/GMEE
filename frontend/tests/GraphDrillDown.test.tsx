import { screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FullCorpusGraph from '../src/components/FullCorpusGraph';
import { clearSelectedArticle, useSelectedArticle } from '../src/lib/useSelectedArticle';
import { jsonResponse, mockApi, renderWithClient } from './helpers';

const articleId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const claimId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
const articleGraph = { nodes: [{ id: articleId, title: 'Actual corpus article', domain: 'source.example', url: 'https://source.example/a', deg: 0 }], edges: [], counts: { nodes: 1, edges: 0 } };

// The selected article hook is exercised by the actual TimelineTunnel tests;
// here the real node selector drives the cross-tab store, without canvas hit mocks.
describe('graph article identity drill-down', () => {
  it('routes a claim node using article_id, never the claim UUID', async () => {
    const navigate = vi.fn();
    mockApi((endpoint) => jsonResponse(endpoint === '/graph/claims'
      ? { nodes: [{ id: claimId, article_id: articleId, title: 'Actual extracted claim', domain: 'source.example', verdict: 'SUPPORTED', prob: 0 }], edges: [], counts: { nodes: 1, edges: 0 } }
      : articleGraph));
    renderWithClient(<FullCorpusGraph setActiveTab={navigate} />);
    await screen.findByRole('option', { name: 'Actual corpus article' });
    fireEvent.click(screen.getByRole('button', { name: 'Claims' }));
    await screen.findByRole('option', { name: 'Actual extracted claim' });
    fireEvent.change(screen.getByLabelText('Inspect a node (keyboard alternative)'), { target: { value: claimId } });
    fireEvent.click(screen.getByRole('button', { name: /View in Timeline/ }));
    expect(navigate).toHaveBeenCalledWith('timeline');
  });

  it('disables unsupported claim timeline navigation when article_id is absent', async () => {
    const navigate = vi.fn();
    mockApi((endpoint) => jsonResponse(endpoint === '/graph/claims'
      ? { nodes: [{ id: claimId, title: 'Claim with no article mapping', domain: 'source.example' }], edges: [], counts: { nodes: 1, edges: 0 } }
      : articleGraph));
    renderWithClient(<FullCorpusGraph setActiveTab={navigate} />);
    await screen.findByRole('option', { name: 'Actual corpus article' });
    fireEvent.click(screen.getByRole('button', { name: 'Claims' }));
    await screen.findByRole('option', { name: 'Claim with no article mapping' });
    fireEvent.change(screen.getByLabelText('Inspect a node (keyboard alternative)'), { target: { value: claimId } });
    const timeline = screen.getByRole('button', { name: /View in Timeline/ });
    expect(timeline.hasAttribute('disabled')).toBe(true);
    expect(timeline.title).toContain('no article_id');
    fireEvent.click(timeline);
    expect(navigate).not.toHaveBeenCalled();
    clearSelectedArticle();
  });
});

void useSelectedArticle;
