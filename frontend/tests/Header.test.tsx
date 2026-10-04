import { describe, expect, it, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Header } from '../src/components/Header';
import { renderWithClient } from './helpers';

const baseProps = { refetchInterval: 5000, setRefetchInterval: vi.fn(), isFetching: false, onManualRefresh: vi.fn() };

describe('dashboard chrome', () => {
  it.each([
    ['connecting', 'Connecting'], ['ready', 'Systems Ready'], ['not_ready', 'Not Ready · Partial Outage'], ['error', 'Connection Failed'],
  ] as const)('reflects the %s readiness state', (status, label) => {
    renderWithClient(<Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status={status} />);
    expect(screen.getByText(label)).toBeTruthy();
  });

  it('activates real dashboard sections and labels polling/refresh controls', () => {
    const setActive = vi.fn();
    renderWithClient(<Header {...baseProps} activeTab="overview" setActiveTab={setActive} status="ready" />);
    fireEvent.click(screen.getByRole('button', { name: /FactCheck/ }));
    expect(setActive).toHaveBeenCalledWith('factcheck');
    expect(screen.getByLabelText('Background polling interval')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Refresh telemetry' })).toBeTruthy();
    expect(screen.queryByText(/6.4k nodes|6.4k articles/)).toBeNull();
  });

  it('marks an explicit demo separately and never fabricates a ready status', () => {
    renderWithClient(<Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status="error" demoMode />);
    expect(screen.getByText('Demo Telemetry')).toBeTruthy();
    expect(screen.getByText('Connection Failed')).toBeTruthy();
    expect(screen.queryByText('Systems Ready')).toBeNull();
  });
});
