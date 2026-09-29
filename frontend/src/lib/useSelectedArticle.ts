import { useSyncExternalStore } from 'react';

/**
 * useSelectedArticle — lightweight cross-tab shared state.
 *
 * When the user clicks a node in FullCorpusGraph or GraphVisualizer and hits
 * "View in Timeline", we store the article reference here. The TimelineTunnel
 * reads it on mount and auto-focuses on the matching cluster.
 *
 * No context provider needed — module-level singleton with useSyncExternalStore.
 */

export interface SelectedArticle {
  id: string;
  title: string;
  domain: string | null;
}

let current: SelectedArticle | null = null;
const listeners = new Set<() => void>();

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function getSnapshot(): SelectedArticle | null {
  return current;
}

export function setSelectedArticle(article: SelectedArticle | null): void {
  current = article;
  listeners.forEach((cb) => cb());
}

export function clearSelectedArticle(): void {
  setSelectedArticle(null);
}

export function useSelectedArticle(): SelectedArticle | null {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
