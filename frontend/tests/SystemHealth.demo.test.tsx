import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SystemHealth } from '../src/pages/SystemHealth';
import { emptyDashboardApi, mockApi, renderWithClient } from './helpers';

describe('explicit optional infrastructure simulator', () => {
  it('starts connecting, with no automatic fabricated telemetry', () => {
    mockApi(() => new Promise<Response>(() => {}));
    const page = renderWithClient(<SystemHealth />);
    expect(screen.getByText('Connecting')).toBeTruthy();
    expect(screen.getByText(/Connecting to backend readiness/)).toBeTruthy();
    expect(screen.getByTestId('loading-grid')).toBeTruthy();
    expect(screen.queryByText(/Demo Telemetry — simulated data stream/)).toBeNull();
    expect(screen.queryByText(/148,920/)).toBeNull();
    page.unmount();
    page.client.clear();
  });

  it('does not activate demo when readiness fails; launch and exit are real explicit controls', async () => {
    window.history.replaceState(null, '', '#/dashboard/cache');
    renderWithClient(<SystemHealth />);
    expect(await screen.findByText('Readiness unavailable')).toBeTruthy();
    expect(screen.queryByText(/Demo Telemetry — simulated data stream/)).toBeNull();
    expect(screen.queryByText('98.4%')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Launch Demo Telemetry' }));
    expect(screen.getByText(/Demo Telemetry — simulated data stream/)).toBeTruthy();
    expect(screen.getByText('98.4%')).toBeTruthy();
    expect(screen.getByText(/Explicit demo — all values below are simulated/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Exit Demo' }));
    expect(screen.queryByText('98.4%')).toBeNull();
    expect(screen.getByText('Readiness unavailable')).toBeTruthy();
  });

  it('does not switch an explicitly chosen demo off behind the user’s back when ready', async () => {
    mockApi(emptyDashboardApi);
    window.history.replaceState(null, '', '#/dashboard/cache');
    renderWithClient(<SystemHealth />);
    await screen.findByText('Systems Ready');
    fireEvent.click(screen.getByRole('button', { name: 'Launch Demo Telemetry' }));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh telemetry' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh telemetry' }).hasAttribute('disabled')).toBe(false));
    expect(screen.getByText(/Demo Telemetry — simulated data stream/)).toBeTruthy();
    expect(screen.getByText('Systems Ready')).toBeTruthy();
  });
});
