import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Landing } from '../src/pages/Landing';
import { emptyDashboardApi, jsonResponse, mockApi, renderWithClient, zeroDashboard } from './helpers';

describe('honest landing statistics', () => {
  it('renders real zero counts without fabricated hero fallback counts', async () => {
    mockApi(emptyDashboardApi);
    renderWithClient(<Landing />);
    const claimLabel = screen.getByText('claims indexed');
    await screen.findByText('3 / 3');
    expect(within(claimLabel.parentElement!).getByText('0')).toBeTruthy();
    expect(within(screen.getByText('graph nodes').parentElement!).getByText('0')).toBeTruthy();
    expect(within(screen.getByText('graph relationships').parentElement!).getByText('0')).toBeTruthy();
    expect(screen.queryByText(/10,000\+|27,132|80,107/)).toBeNull();
    expect(screen.getByText(/decorative globe/)).toBeTruthy();
  });

  it('keeps initial/unavailable counts unknown and offers actual retry', async () => {
    let failure = true;
    const fetch = mockApi((endpoint) => endpoint === '/dashboard' ? failure ? jsonResponse({ detail: 'Dashboard unavailable' }, 503) : jsonResponse(zeroDashboard) : emptyDashboardApi(endpoint));
    renderWithClient(<Landing />);
    expect(screen.getByText('Connecting to real dashboard metrics…')).toBeTruthy();
    expect(await screen.findByText('Dashboard unavailable')).toBeTruthy();
    expect(within(screen.getByText('claims indexed').parentElement!).getByText('—')).toBeTruthy();
    expect(screen.queryByText('3 / 3')).toBeNull();
    failure = false;
    fireEvent.click(screen.getByRole('button', { name: /Retry dashboard metrics/ }));
    expect(await screen.findByText('3 / 3')).toBeTruthy();
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith('/dashboard'))).toHaveLength(2);
  });
});
