import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Header } from '../src/components/Header';

const baseProps = {
  refetchInterval: 5000,
  setRefetchInterval: vi.fn(),
  isFetching: false,
  onManualRefresh: vi.fn(),
};

describe('<Header/> — dashboard chrome', () => {
  it('reflects service status through the badge label', () => {
    const { unmount } = render(<Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status="ok" />);
    expect(screen.getByText('Systems Nominal')).toBeTruthy();
    unmount();

    const r2 = render(<Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status="degraded" />);
    expect(screen.getByText('Degraded State')).toBeTruthy();
    r2.unmount();

    const r3 = render(<Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status="error" />);
    expect(screen.getByText('Connection Failed')).toBeTruthy();
    r3.unmount();
  });

  it('activates tabs via setActiveTab callback', () => {
    const setActive = vi.fn();
    render(
      <Header {...baseProps} activeTab="overview" setActiveTab={setActive} status="ok" />,
    );
    fireEvent.click(screen.getByText('FactCheck'));
    expect(setActive).toHaveBeenCalledWith('factcheck');
  });

  it('shows demo telemetry state distinctly when backend never answered', () => {
    render(
      <Header {...baseProps} activeTab="overview" setActiveTab={vi.fn()} status="error" demoMode />,
    );
    expect(screen.getByText('Connection Failed')).toBeTruthy();
  });
});
