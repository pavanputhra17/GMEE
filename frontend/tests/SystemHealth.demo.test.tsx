import { render, screen, waitFor } from '@testing-library/react';
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

describe('SystemHealth demo-mode behavior', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('auto-activates labeled DEMO TELEMETRY when backend unreachable', async () => {
    renderPage();

    // After the health query fails, demo mode engages with its banner.
    // (Instant rejection skips the skeleton phase entirely — intended.)
    await waitFor(
      () => {
        expect(screen.getByText(/Demo Telemetry — simulated data stream/i)).toBeDefined();
      },
      { timeout: 4000 },
    );
    expect(screen.getByText(/Exit Demo/i)).toBeDefined();
  });
});
