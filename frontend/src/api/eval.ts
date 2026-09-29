import { apiClient } from './client';

export type EvalLabel = 'SAME_STORY' | 'EVOLVED' | 'DISTINCT';

export interface EvalClaimSide {
  text: string;
  domain: string;
}

export interface EvalPair {
  pair_id: string;
  a: EvalClaimSide;
  b: EvalClaimSide;
}

export interface EvalNext {
  done: boolean;
  pair: EvalPair | null;
}

export interface EvalBucketProgress {
  bucket: string;
  pairs: number;
  labeled: number;
}

export interface EvalProgress {
  total_pairs: number;
  labeled_votes: number;
  labeled_pairs_distinct: number;
  by_bucket: EvalBucketProgress[];
  per_annotator: Record<string, { labels: Record<string, number>; total: number }>;
  inter_annotator: Array<{ annotators: string[]; pairs: number; kappa: number }>;
  complete: boolean;
}

export interface EvalLabelResult {
  status: string;
  pair_id: string;
  label: string;
}

const ANNOTATOR_KEY = 'gmee-eval-annotator';

export const evalApi = {
  annotatorKey: ANNOTATOR_KEY,

  loadAnnotator: (): string => {
    try {
      return window.localStorage.getItem(ANNOTATOR_KEY) ?? '';
    } catch {
      return '';
    }
  },

  saveAnnotator: (name: string): void => {
    try {
      window.localStorage.setItem(ANNOTATOR_KEY, name);
    } catch {
      /* storage unavailable (private mode) — annotator just won't persist */
    }
  },

  next: (annotator: string) =>
    apiClient.get(`/eval/next?annotator=${encodeURIComponent(annotator)}`) as Promise<EvalNext>,

  label: (pairId: string, annotator: string, label: EvalLabel) =>
    apiClient.post('/eval/label', {
      pair_id: pairId,
      annotator,
      label,
    }) as Promise<EvalLabelResult>,

  progress: () => apiClient.get('/eval/progress') as Promise<EvalProgress>,
};
