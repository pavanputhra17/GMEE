import { screen, waitFor, fireEvent, act } from '@testing-library/react';
import { focusManager } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { SystemHealth } from '../src/pages/SystemHealth';
import { emptyDashboardApi, jsonResponse, mockApi, renderWithClient, zeroDashboard } from './helpers';

const TABS = ['overview', 'graph', 'vector', 'cache', 'corpus', 'factcheck', 'fullgraph', 'timeline', 'masala', 'eval'] as const;

describe('real readiness, independent tabs and shared polling', () => {
  it('renders ready and legitimate zero infrastructure counts, not demo fallbacks', async () => {
    mockApi(emptyDashboardApi);
    renderWithClient(<SystemHealth />);
    expect(await screen.findByText('Systems Ready')).toBeTruthy();
    expect(screen.getByText('0 claims')).toBeTruthy();
    expect(screen.getByText('0 nodes · 0 edges')).toBeTruthy();
    expect(screen.getByText('3 / 3 ready')).toBeTruthy();
    expect(screen.queryByText(/Demo Telemetry — simulated data stream/)).toBeNull();
    expect(screen.queryByText(/42,118|137,540|128.4 MB/)).toBeNull();
  });

  it('retains readiness dependencies on 503 and keeps Postgres-backed tabs usable', async () => {
    const partial = { status: 'not_ready', postgres: 'ok', neo4j: 'down: graph unavailable', redis: 'ok' };
    mockApi((endpoint) => {
      if (endpoint === '/health/ready') return jsonResponse(partial, 503);
      if (endpoint === '/dashboard') return jsonResponse({ ...zeroDashboard, graph: null, services: { ...zeroDashboard.services, neo4j: partial.neo4j } });
      return emptyDashboardApi(endpoint);
    });
    renderWithClient(<SystemHealth />);
    expect(await screen.findByText('Not Ready · Partial Outage')).toBeTruthy();
    expect(screen.getByText('down: graph unavailable')).toBeTruthy();
    expect(screen.queryByText('Readiness unavailable')).toBeNull();
    expect(screen.getByText('2 / 3 ready')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /^Corpus$/ }));
    expect(await screen.findByText('No articles match this search.')).toBeTruthy();
    expect(screen.getByText('0 articles')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /FactCheck/ }));
    expect(await screen.findByText(/No verdicts yet for this filter/)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Corpus Evidence Check' })).toBeTruthy();
  });

  it('shows only actual Redis memory and marks unreported cache metrics unknown', async () => {
    mockApi(emptyDashboardApi);
    window.history.replaceState(null, '', '#/dashboard/cache');
    renderWithClient(<SystemHealth />);
    expect(await screen.findByText('0 MB')).toBeTruthy();
    expect(screen.getAllByText('Not reported')).toHaveLength(2);
    expect(screen.queryByText(/98.4%|0.2ms|1,409|128.4 MB/)).toBeNull();
  });

  it.each(TABS)('mounts the real "%s" tab even if readiness cannot be reached', async (tab) => {
    window.history.replaceState(null, '', `#/dashboard/${tab}`);
    mockApi((endpoint) => endpoint === '/health/ready' ? Promise.reject(new TypeError('Readiness network failure')) : emptyDashboardApi(endpoint));
    renderWithClient(<SystemHealth />);
    expect(await screen.findByText('Readiness unavailable')).toBeTruthy();
    expect(screen.getByText('Connection Failed')).toBeTruthy();
    expect(screen.queryByText(/Demo Telemetry — simulated data stream/)).toBeNull();
    if (tab === 'cache') expect(screen.getByText(/Redis Cache & Token Blocklist Telemetry/)).toBeTruthy();
    if (tab === 'eval') expect(screen.getByText(/Sign in to use Eval Lab/)).toBeTruthy();
    if (tab === 'masala') expect(screen.getByRole('heading', { name: 'Mutation Comparator' })).toBeTruthy();
  });

  it('syncs tabs with hash changes and actual browser Back navigation', async () => {
    mockApi(emptyDashboardApi);
    window.history.replaceState(null, '', '#/dashboard/corpus');
    renderWithClient(<SystemHealth />);
    await screen.findByText('Article Corpus');
    fireEvent.click(screen.getByRole('button', { name: /Redis Queue/ }));
    await screen.findByText(/Redis Cache & Token Blocklist Telemetry/);
    expect(window.location.hash).toBe('#/dashboard/cache');
    window.history.back();
    expect(await screen.findByText('Article Corpus')).toBeTruthy();
    await waitFor(() => expect(window.location.hash).toBe('#/dashboard/corpus'));
    act(() => { window.location.hash = '#/dashboard/factcheck'; window.dispatchEvent(new HashChangeEvent('hashchange')); });
    expect(await screen.findByRole('heading', { name: 'Corpus Evidence Check' })).toBeTruthy();
  });

  it('pauses every mounted background query and focus refetch, while new tabs can still fetch', async () => {
    vi.useFakeTimers();
    const fetch = mockApi(emptyDashboardApi);
    window.history.replaceState(null, '', '#/dashboard/corpus');
    const page = renderWithClient(<SystemHealth />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(screen.getByText('No articles match this search.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Background polling interval'), { target: { value: '0' } });
    const beforePause = fetch.mock.calls.length;
    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      await vi.advanceTimersByTimeAsync(90_000);
    });
    expect(fetch).toHaveBeenCalledTimes(beforePause);
    fireEvent.click(screen.getByRole('button', { name: /FactCheck/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/verdicts'))).toBe(true);
    expect(screen.getByText(/No verdicts yet for this filter/)).toBeTruthy();
    const afterMount = fetch.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetch).toHaveBeenCalledTimes(afterMount);
    page.unmount();
    page.client.clear();
    focusManager.setFocused(undefined);
  });
});
