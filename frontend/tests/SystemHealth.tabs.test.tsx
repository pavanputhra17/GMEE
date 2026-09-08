/**
 * SystemHealth page-body coverage: demo latch, manual demo/error state
 * machine, and every dashboard tab branch.
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemHealth } from '../src/pages/SystemHealth';

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SystemHealth />
    </QueryClientProvider>,
  );
}

const TABS = ['overview', 'graph', 'vector', 'cache', 'corpus', 'factcheck', 'fullgraph', 'timeline', 'masala'] as const;

describe('SystemHealth page body', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('renders all four overview MetricCards in demo mode', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Demo Telemetry — simulated data stream/i)).toBeTruthy(), {
      timeout: 4000,
    });
    expect(screen.getByText('PostgreSQL Vector')).toBeTruthy();
    // "Neo4j Graph Engine" appears twice: overview card + nav tab
    expect(screen.getAllByText('Neo4j Graph Engine').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Redis Cache & Queue')).toBeTruthy();
    expect(screen.getByText('System Health Score')).toBeTruthy();
  });

  it('Exit Demo reveals the severance error view, Launch Demo restores simulation', async () => {
    const utils = renderPage();
    await waitFor(() => expect(screen.getByText(/Exit Demo/i)).toBeTruthy(), { timeout: 4000 });

    fireEvent.click(screen.getByText(/Exit Demo/i));
    expect(await screen.findByText(/Backend Connection Severed/i)).toBeTruthy();
    expect(screen.getByText(/Re-try Telemetry Handshake/i)).toBeTruthy();

    fireEvent.click(screen.getByText(/Launch Demo Telemetry/i));
    expect(await screen.findByText(/Demo Telemetry — simulated data stream/i)).toBeTruthy();
    utils.unmount();
  });

  it.each(TABS)('activates the "%s" tab branch via deep link', async (tab) => {
    window.location.hash = `#/dashboard/${tab}`;
    renderPage();
    // Every tab still mounts the chrome; branch-specific content differs.
    await waitFor(() => expect(screen.getByText(/Systems Nominal|Connection Failed|Degraded State/)).toBeTruthy(), {
      timeout: 4000,
    });
    if (tab === 'cache') {
      expect(await screen.findByText(/Redis Cache & Token Blocklist Telemetry/)).toBeTruthy();
    }
    if (tab === 'corpus') {
      expect(await screen.findByText('Story Clusters')).toBeTruthy();
    }
  });
});
