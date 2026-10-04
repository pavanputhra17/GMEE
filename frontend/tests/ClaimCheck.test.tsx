import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ClaimCheck } from '../src/components/ClaimCheck';
import { jsonResponse, mockApi, renderWithClient, signInFixture } from './helpers';

const evidence = {
  claim_id: 'claim-1', article_id: 'article-1', text: 'The river level increased by two metres.',
  passage: 'The monitoring station recorded a two-metre increase on Tuesday.', passage_source: 'cleaned_content',
  url: 'https://source.example/report', title: 'River monitoring report', domain: 'source.example',
  published_at: '2026-09-20T09:00:00Z', similarity: 0.87, stance: 'entailment', syndication_group: 'syndication-1',
};
const result = {
  claim_text: 'The river level increased by two metres.', assessment: 'SUPPORTED_BY_CORPUS', evidence: [evidence],
  warnings: ['Different domains may share a syndicated source.'], score_kind: 'uncalibrated_heuristic',
  observed_at: '2026-10-03T10:00:00Z', method_version: 'actual-method-v1',
};

function submitClaim() {
  fireEvent.change(screen.getByLabelText('Claim to check'), { target: { value: result.claim_text } });
  fireEvent.click(screen.getByRole('button', { name: 'Check corpus evidence' }));
}

describe('corpus evidence checking', () => {
  it('requires authentication without sending a request or showing fake evidence', () => {
    const fetch = mockApi(() => jsonResponse(result));
    renderWithClient(<ClaimCheck />);
    expect(screen.getByText(/Sign in to use corpus evidence checking/)).toBeTruthy();
    expect(screen.queryByLabelText('Claim to check')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('sends claim_text, an ISO publication cutoff and limit 8 with bearer auth', async () => {
    signInFixture();
    const fetch = mockApi(() => jsonResponse(result));
    renderWithClient(<ClaimCheck />);
    fireEvent.change(screen.getByLabelText('Claim to check'), { target: { value: ` ${result.claim_text} ` } });
    const cutoff = '2026-09-20T12:30';
    fireEvent.change(screen.getByLabelText('As of (optional, local time)'), { target: { value: cutoff } });
    fireEvent.click(screen.getByRole('button', { name: 'Check corpus evidence' }));
    await screen.findByRole('heading', { name: 'Supported by corpus' });
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ claim_text: result.claim_text, as_of: new Date(cutoff).toISOString(), limit: 8 });
    expect(String(fetch.mock.calls[0][0])).toContain('/verdicts/check');
    expect(new Headers(fetch.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer test-access');
    expect(screen.getByLabelText('Claim to check').getAttribute('maxlength')).toBe('2000');
  });

  it('displays actual passages, stances, source URLs and limitations; rejects unsafe URLs', async () => {
    signInFixture();
    mockApi(() => jsonResponse({ ...result, evidence: [evidence, { ...evidence, claim_id: 'claim-2', article_id: 'article-2', title: 'Unsafe source title', url: 'javascript:alert(1)', passage_source: 'extracted_claim' }] }));
    renderWithClient(<ClaimCheck />);
    submitClaim();
    expect((await screen.findAllByText(evidence.passage)).length).toBe(2);
    expect(screen.getByRole('link', { name: /River monitoring report/ }).getAttribute('href')).toBe(evidence.url);
    expect(screen.queryByRole('link', { name: /Unsafe source title/ })).toBeNull();
    expect(screen.getByText(/HTTP\/HTTPS required/)).toBeTruthy();
    expect(screen.getByText(/extracted claim text, not an article-body quotation/)).toBeTruthy();
    expect(screen.getByText('Different domains may share a syndicated source.')).toBeTruthy();
    expect(screen.getByText(/uncalibrated_heuristic/)).toBeTruthy();
    expect(screen.getByText(/not probabilities of truth/)).toBeTruthy();
    expect(screen.getAllByText(/Syndication group:/)).toHaveLength(2);
  });

  it.each([
    ['SUPPORTED_BY_CORPUS', 'Supported by corpus'], ['CONTRADICTED_BY_CORPUS', 'Contradicted by corpus'],
    ['MIXED_EVIDENCE', 'Mixed evidence'], ['INSUFFICIENT_EVIDENCE', 'Insufficient evidence'],
  ])('renders %s as a corpus assessment rather than true/false', async (assessment, label) => {
    signInFixture();
    mockApi(() => jsonResponse({ ...result, assessment, evidence: [], warnings: [] }));
    renderWithClient(<ClaimCheck />);
    submitClaim();
    expect(await screen.findByRole('heading', { name: label })).toBeTruthy();
    expect(screen.getByText(/No matching corpus evidence returned/)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /^(true|false)$/i })).toBeNull();
  });

  it('does not treat retrieval failure as insufficient evidence and retries the actual request', async () => {
    signInFixture();
    let failure = true;
    const fetch = mockApi(() => failure ? jsonResponse({ detail: 'NLI model unavailable' }, 503) : jsonResponse({ ...result, assessment: 'INSUFFICIENT_EVIDENCE', evidence: [] }));
    renderWithClient(<ClaimCheck />);
    submitClaim();
    expect(await screen.findByText('NLI model unavailable')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Insufficient evidence' })).toBeNull();
    failure = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry corpus evidence check/ }));
    expect(await screen.findByRole('heading', { name: 'Insufficient evidence' })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('keeps the initial form empty and prevents an undersized claim', () => {
    signInFixture();
    const fetch = mockApi(() => jsonResponse(result));
    renderWithClient(<ClaimCheck />);
    expect(screen.getByText(/No evidence check has been run/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Claim to check'), { target: { value: 'short' } });
    expect(screen.getByRole('button', { name: 'Check corpus evidence' }).hasAttribute('disabled')).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });
});
