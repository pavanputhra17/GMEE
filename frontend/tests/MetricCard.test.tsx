import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { MetricCard } from '../src/components/MetricCard';
import { Database, Network } from 'lucide-react';

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('MetricCard', () => {
  it('renders title, value and trend chip', () => {
    renderWithClient(
      <MetricCard
        title="PostgreSQL Vector"
        value="Nominal"
        subtitle="Relational DB & pgvector"
        icon={Database}
        accentColor="violet"
        trend="PORT 55432"
        trendPositive={true}
      />,
    );
    expect(screen.getByText('PostgreSQL Vector')).toBeDefined();
    expect(screen.getByText('Nominal')).toBeDefined();
    expect(screen.getByText('PORT 55432')).toBeDefined();
    expect(screen.getByText(/Relational DB & pgvector/)).toBeDefined();
  });

  it('shows DOWN styling state without crashing on negative trend', () => {
    renderWithClient(
      <MetricCard
        title="Neo4j Graph Engine"
        value="Degraded"
        subtitle="Claims propagation network"
        icon={Network}
        accentColor="rose"
        trend="DOWN"
        trendPositive={false}
      />,
    );
    expect(screen.getByText('Degraded')).toBeDefined();
    expect(screen.getByText('DOWN')).toBeDefined();
  });
});
