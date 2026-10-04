import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { clearSession } from '../src/lib/session';
import { clearSelectedArticle } from '../src/lib/useSelectedArticle';

beforeEach(() => {
  // Canvas rendering is a browser concern; jsdom's unimplemented context
  // otherwise logs on every frame. API and UI state logic remain real.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query === '(prefers-reduced-motion: reduce)', media: query,
    onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  })));
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Unmocked API request'); }));
  window.history.replaceState(null, '', '/');
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearSession();
  clearSelectedArticle();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
