import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../src/App';
import { describe, it, expect } from 'vitest';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

describe('App Component', () => {
  it('renders GMEE Command Center page', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    );
    expect(screen.getByText('GMEE')).toBeDefined();
    expect(screen.getByText('Global Misinformation Evolution Engine')).toBeDefined();
  });
});
