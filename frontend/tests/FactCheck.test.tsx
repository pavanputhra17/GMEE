import { describe, expect, it } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { FactCheck } from '../src/components/FactCheck';
import { jsonResponse, mockApi, renderWithClient } from './helpers';

const row = {
  id: '11111111-1111-1111-1111-111111111111', claim_text: 'Global average temperature rose in the last decade.',
  verdict: 'SUPPORTED', probability: 0.81, extraction_confidence: 0.93, outlet: 'example-news.com',
  article_title: 'Climate study published', article_url: 'https://example-news.com/article',
};
const detail = {
  ...row, verdict_rationale: 'Returned stored rationale; corpus corroboration is incomplete.',
  verdict_evidence: { corroboration: { value: 0.9, weight: 0.4 }, score_kind: 'uncalibrated_heuristic', checked_neighbors: [] },
};

function responses(endpoint: string): Response {
  if (endpoint === '/verdicts/leaderboard') return jsonResponse({ ranking: [{ name: 'example-news.com', claims: 5, supported: 3, disputed: 1, credibility: 0.6 }] });
  if (endpoint === '/verdicts/stats') return jsonResponse({ total_claims: 0, distribution: [], outlets: [] });
  if (endpoint.endsWith(row.id)) return jsonResponse(detail);
  if (endpoint === '/verdicts/feedback') return jsonResponse({ status: 'recorded', claim_id: row.id, vote: 'AGREE', feedback_kind: 'anonymous_unverified' }, 201);
  return jsonResponse({ total: 1, items: [row] });
}

describe('stored FactCheck evidence and uncertainty', () => {
  it('renders the stored score as heuristic/unvalidated, not calibrated probability', async () => {
    mockApi(responses);
    renderWithClient(<FactCheck />);
    expect(await screen.findByText(row.claim_text)).toBeTruthy();
    expect(screen.getByText('81.0%')).toBeTruthy();
    expect(screen.getByText('Heuristic support · unvalidated')).toBeTruthy();
    expect(screen.getByText(/uncalibrated, unvalidated heuristics/)).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
    expect(screen.queryByText('P(supported)')).toBeNull();
  });

  it('never substitutes 50% for a missing stored score', async () => {
    mockApi((endpoint) => endpoint === '/verdicts' ? jsonResponse({ total: 1, items: [{ ...row, probability: null }] }) : responses(endpoint));
    renderWithClient(<FactCheck />);
    expect(await screen.findByText('Not scored')).toBeTruthy();
    expect(screen.queryByText('50.0%')).toBeNull();
  });

  it('distinguishes successful empty data from errors and can retry the real feed', async () => {
    let failure = true;
    mockApi((endpoint) => endpoint === '/verdicts' ? failure ? jsonResponse({ detail: 'Verdicts store unavailable' }, 503) : jsonResponse({ total: 0, items: [] }) : responses(endpoint));
    renderWithClient(<FactCheck />);
    expect(await screen.findByText('Verdict feed unavailable')).toBeTruthy();
    expect(screen.queryByText(/No verdicts yet/)).toBeNull();
    failure = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry verdict feed/ }));
    expect(await screen.findByText(/No verdicts yet for this filter/)).toBeTruthy();
  });

  it('records anonymous feedback from the actual accessible evidence drawer', async () => {
    const fetch = mockApi(responses);
    renderWithClient(<FactCheck />);
    fireEvent.click(await screen.findByRole('button', { name: `Inspect evidence for ${row.claim_text}` }));
    expect(await screen.findByRole('dialog', { name: /Verdict Dossier/ })).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: 'Agree with engine' }));
    expect(await screen.findByText(/Vote recorded/)).toBeTruthy();
    const request = fetch.mock.calls.find(([url]) => String(url).endsWith('/verdicts/feedback'));
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ claim_id: row.id, vote: 'AGREE', corrected_verdict: null });
    expect(screen.queryByText(/NaN/)).toBeNull();
  });

  it('does not leave a failed detail request in a perpetual loading dialog', async () => {
    let failure = true;
    mockApi((endpoint) => endpoint.endsWith(row.id) && failure ? jsonResponse({ detail: 'Evidence detail unavailable' }, 503) : responses(endpoint));
    renderWithClient(<FactCheck />);
    const opener = await screen.findByRole('button', { name: `Inspect evidence for ${row.claim_text}` });
    opener.focus();
    fireEvent.click(opener);
    expect(await screen.findByText('Evidence detail unavailable')).toBeTruthy();
    failure = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry verdict detail/ }));
    await screen.findByText(detail.verdict_rationale);
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  it('reports statistics and outlet errors separately from the usable verdict feed', async () => {
    mockApi((endpoint) => endpoint === '/verdicts/stats' || endpoint === '/verdicts/leaderboard' ? jsonResponse({ detail: 'Aggregate unavailable' }, 503) : responses(endpoint));
    renderWithClient(<FactCheck />);
    expect(await screen.findByText(row.claim_text)).toBeTruthy();
    expect(screen.getByText('Verdict statistics unavailable')).toBeTruthy();
    expect(screen.getByText('Outlet scores unavailable')).toBeTruthy();
  });
});
