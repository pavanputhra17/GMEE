import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MutationComparator } from '../src/components/MutationComparator';
import { jsonResponse, mockApi, renderWithClient, signInFixture } from './helpers';

const result = {
  analysis: {
    mutation_types: ['NUMERIC_SHIFT'], observed_propagation: false,
    changed_spans: [{ operation: 'replace', older_span: { start: 10, end: 12, text: '12' }, newer_span: { start: 10, end: 12, text: '18' }, kinds: ['numeric'] }],
    similarity: 0.8, algorithm_version: 'returned-method-v1', limitations: ['Text comparison is inferred, not observed transmission.'],
  },
};

function fillComparison() {
  fireEvent.change(screen.getByLabelText('Older text'), { target: { value: 'Officials said 12 homes were affected.' } });
  fireEvent.change(screen.getByLabelText('Newer text'), { target: { value: 'Officials said 18 homes were affected.' } });
}

describe('authenticated mutation comparator', () => {
  it('requires sign-in without inventing a comparison or making a private request', () => {
    const fetch = mockApi(() => jsonResponse(result));
    renderWithClient(<MutationComparator />);
    expect(screen.getByText(/Sign in to use the mutation comparator/)).toBeTruthy();
    expect(screen.queryByLabelText('Older text')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('submits original texts and displays real typed spans and nested propagation limitations', async () => {
    signInFixture();
    const fetch = mockApi(() => jsonResponse(result));
    renderWithClient(<MutationComparator />);
    expect(screen.getByRole('button', { name: 'Compare mutations' }).hasAttribute('disabled')).toBe(true);
    fireEvent.change(screen.getByLabelText('Older text'), { target: { value: '  Officials said 12 homes were affected.  ' } });
    fireEvent.change(screen.getByLabelText('Newer text'), { target: { value: 'Officials said 18 homes were affected.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Compare mutations' }));
    expect(await screen.findByText('NUMERIC_SHIFT')).toBeTruthy();
    expect(screen.getByText(/No observed propagation/)).toBeTruthy();
    expect(screen.getByText('“12”')).toBeTruthy();
    expect(screen.getByText('“18”')).toBeTruthy();
    expect(screen.getByText('Text comparison is inferred, not observed transmission.', { selector: 'li' })).toBeTruthy();
    expect(String(fetch.mock.calls[0][0])).toContain('/graph/mutation/compare');
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ older_text: '  Officials said 12 homes were affected.  ', newer_text: 'Officials said 18 homes were affected.' });
    expect(new Headers(fetch.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer test-access');
    expect(screen.getByLabelText('Older text').getAttribute('maxlength')).toBe('2000');
  });

  it('accepts legacy segment/additive analysis fields without manufacturing missing changes', async () => {
    signInFixture();
    mockApi(() => jsonResponse({ analysis: { mutation_types: [], segments: [{ type: 'changed', old: 'could', new: 'will', kinds: ['hedge'] }], future_field: { returned: 'actual value' } }, observed_propagation: false }));
    renderWithClient(<MutationComparator />);
    fillComparison();
    fireEvent.click(screen.getByRole('button', { name: 'Compare mutations' }));
    expect(await screen.findByText(/No mutation types reported/)).toBeTruthy();
    expect(screen.getByText('“could”')).toBeTruthy();
    expect(screen.getByText('“will”')).toBeTruthy();
    expect(screen.getByText(/actual value/)).toBeTruthy();
  });

  it('shows an API error with a real retry instead of an empty/success result', async () => {
    signInFixture();
    let failure = true;
    const fetch = mockApi(() => failure ? jsonResponse({ detail: 'Mutation service unavailable' }, 503) : jsonResponse(result));
    renderWithClient(<MutationComparator />);
    fillComparison();
    fireEvent.click(screen.getByRole('button', { name: 'Compare mutations' }));
    expect(await screen.findByText('Mutation service unavailable')).toBeTruthy();
    expect(screen.queryByText('NUMERIC_SHIFT')).toBeNull();
    failure = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry mutation comparison/ }));
    expect(await screen.findByText('NUMERIC_SHIFT')).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('exposes loading and caller cancellation without leaving a perpetual spinner', async () => {
    signInFixture();
    const fetch = mockApi(() => new Promise<Response>(() => {}));
    renderWithClient(<MutationComparator />);
    fillComparison();
    fireEvent.click(screen.getByRole('button', { name: 'Compare mutations' }));
    await screen.findByText('Waiting for mutation analysis…');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel comparison' }));
    expect(await screen.findByText('Request cancelled.')).toBeTruthy();
    await waitFor(() => expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true));
    expect(screen.queryByText('Waiting for mutation analysis…')).toBeNull();
  });
});
