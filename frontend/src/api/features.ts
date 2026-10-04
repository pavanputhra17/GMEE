import { apiClient, type ApiRequestOptions } from './client';

export interface MutationComparisonInput { older_text: string; newer_text: string }
export interface MutationComparison {
  analysis: { mutation_types: string[]; [key: string]: unknown };
  llm_summary?: string;
  observed_propagation?: boolean;
  warnings?: string[];
}

export type CorpusAssessment = 'SUPPORTED_BY_CORPUS' | 'CONTRADICTED_BY_CORPUS' | 'MIXED_EVIDENCE' | 'INSUFFICIENT_EVIDENCE';
export interface ClaimCheckInput { claim_text: string; as_of?: string; limit: number }
export interface CorpusEvidence {
  claim_id: string;
  article_id: string;
  text: string;
  passage: string | null;
  passage_source?: 'cleaned_content' | 'content' | 'extracted_claim';
  url: string | null;
  title: string | null;
  domain: string | null;
  published_at: string | null;
  similarity: number;
  stance: 'entailment' | 'contradiction' | 'neutral';
  syndication_group: string | null;
}
export interface ClaimCheckResult {
  claim_text: string;
  assessment: CorpusAssessment;
  evidence: CorpusEvidence[];
  warnings: string[];
  score_kind: 'uncalibrated_heuristic';
  observed_at: string;
  method_version: string;
}

export interface ExternalCheckResult {
  claim: string;
  verdict: 'SUPPORTED' | 'DISPUTED' | 'UNVERIFIABLE';
  explanation: string;
  sources: { title: string; url: string }[];
}

export const featuresApi = {
  compare: (input: MutationComparisonInput, options?: ApiRequestOptions) =>
    apiClient.post<MutationComparison>('/graph/mutation/compare', input, { timeoutMs: 45_000, ...options, authenticated: true }),
  check: (input: ClaimCheckInput, options?: ApiRequestOptions) =>
    apiClient.post<ClaimCheckResult>('/verdicts/check', input, { timeoutMs: 45_000, ...options, authenticated: true }),
  checkExternal: (input: ClaimCheckInput, options?: ApiRequestOptions) =>
    apiClient.post<ExternalCheckResult>('/verdicts/check-external', input, { timeoutMs: 60_000, ...options, authenticated: true }),
};

