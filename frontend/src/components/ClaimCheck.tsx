import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { FileSearch, ExternalLink } from 'lucide-react';
import { featuresApi, type ClaimCheckInput, type CorpusAssessment } from '../api/features';
import { useSession } from '../lib/session';
import { safeHttpUrl } from '../lib/urls';
import { QueryError } from './QueryError';
import { SignInNotice } from './SignInNotice';

const ASSESSMENTS: Record<CorpusAssessment, string> = {
  SUPPORTED_BY_CORPUS: 'Supported by corpus',
  CONTRADICTED_BY_CORPUS: 'Contradicted by corpus',
  MIXED_EVIDENCE: 'Mixed evidence',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

function CheckForm() {
  const [claim, setClaim] = useState('');
  const [asOf, setAsOf] = useState('');
  const controller = useRef<AbortController | null>(null);
  const id = useId();
  useEffect(() => () => controller.current?.abort(), []);
  const check = useMutation({
    mutationFn: (input: ClaimCheckInput) => {
      controller.current = new AbortController();
      return featuresApi.check(input, { signal: controller.current.signal });
    },
  });
  const checkExternal = useMutation({
    mutationFn: (input: ClaimCheckInput) => {
      controller.current = new AbortController();
      return featuresApi.checkExternal(input, { signal: controller.current.signal });
    },
  });
  
  const input = (): ClaimCheckInput => ({ claim_text: claim.trim(), limit: 8, ...(asOf ? { as_of: new Date(asOf).toISOString() } : {}) });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!check.isPending && claim.trim().length >= 10) check.mutate(input());
  };
  const submitExternal = (event: React.MouseEvent) => {
    event.preventDefault();
    if (!checkExternal.isPending && claim.trim().length >= 10) checkExternal.mutate(input());
  };
  
  const result = check.data;
  const extResult = checkExternal.data;

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor={`${id}-claim`} className="block text-xs font-mono mb-2">Claim to check</label>
          <textarea id={`${id}-claim`} required minLength={10} rows={3} maxLength={2000} value={claim} disabled={check.isPending || checkExternal.isPending} onChange={(event) => { setClaim(event.target.value); check.reset(); checkExternal.reset(); }} className="field-brutal w-full" />
        </div>
        <div>
          <label htmlFor={`${id}-asof`} className="block text-xs font-mono mb-2">As of (optional, local time)</label>
          <input id={`${id}-asof`} type="datetime-local" value={asOf} disabled={check.isPending || checkExternal.isPending} onChange={(event) => { setAsOf(event.target.value); check.reset(); checkExternal.reset(); }} className="field-brutal" aria-describedby={`${id}-asof-hint`} />
          <p id={`${id}-asof-hint`} className="text-xs text-hermes-bone/50 mt-1">Restrict evidence to this publication cutoff. This is a query over today's corpus, not a historical corpus snapshot.</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button type="submit" disabled={check.isPending || checkExternal.isPending || claim.trim().length < 10} className="btn-brutal">{check.isPending ? 'Checking corpus…' : 'Check corpus evidence'}</button>
          <button type="button" onClick={submitExternal} disabled={check.isPending || checkExternal.isPending || claim.trim().length < 10} className="btn-brutal bg-emerald-500/10 text-emerald-300 border-emerald-500/30">{checkExternal.isPending ? 'Grounding externally…' : 'Ground Externally (Wikipedia RAG)'}</button>
          {(check.isPending || checkExternal.isPending) && <button type="button" onClick={() => controller.current?.abort()} className="btn-brutal">Cancel evidence check</button>}
        </div>
      </form>
      {check.isIdle && checkExternal.isIdle && <p className="text-xs font-mono text-hermes-bone/55">No evidence check has been run. Submit a claim to retrieve up to 8 corpus passages or ground externally.</p>}
      {check.isPending && <p role="status" className="text-xs font-mono">Retrieving and assessing corpus evidence…</p>}
      {checkExternal.isPending && <p role="status" className="text-xs font-mono text-emerald-300">Searching Wikipedia and running LLM fact-checker...</p>}
      {check.isError && <QueryError title="Corpus evidence check unavailable" error={check.error} onRetry={() => check.mutate(input())} />}
      {checkExternal.isError && <QueryError title="External grounding unavailable" error={checkExternal.error} onRetry={() => checkExternal.mutate(input())} />}
      
      {extResult && <div aria-live="polite" className="space-y-4">
        <div className="border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-2">
           <h3 className="font-display text-xl text-emerald-300">External Grounding: {extResult.verdict}</h3>
           <p className="text-sm">{extResult.claim}</p>
           <p className="text-sm text-emerald-100">{extResult.explanation}</p>
           {extResult.sources.length > 0 && (
             <div className="mt-4 border-t border-emerald-500/20 pt-2">
               <h4 className="text-xs font-mono text-emerald-400 mb-2">Wikipedia Sources Used:</h4>
               <ul className="text-xs space-y-1">
                 {extResult.sources.map((s, i) => (
                   <li key={i}><a href={s.url} target="_blank" rel="noopener noreferrer" className="text-emerald-300 hover:underline inline-flex items-center gap-1">{s.title} <ExternalLink className="w-3 h-3"/></a></li>
                 ))}
               </ul>
             </div>
           )}
        </div>
      </div>}
      
      {result && <div aria-live="polite" className="space-y-4">
        <div className="border border-hermes-bone/20 bg-hermes-panel-deep p-4 space-y-2">
          <h3 className="font-display text-xl">{ASSESSMENTS[result.assessment] ?? result.assessment}</h3>
          <p className="text-sm">{result.claim_text}</p>
          <p className="text-xs font-mono text-amber-300">Corpus assessment, not a true/false verdict. Missing or conflicting evidence remains uncertain.</p>
          <p className="text-xs font-mono text-hermes-bone/60">Score kind: {result.score_kind} · method: {result.method_version} · observed: {result.observed_at}</p>
          <p className="text-xs text-hermes-bone/55">Similarity and stance are uncalibrated heuristic signals, not probabilities of truth.</p>
        </div>
        {result.warnings.length > 0 && <div className="border border-amber-300/30 p-3">
          <h4 className="text-xs font-mono mb-2">Warnings and limitations</h4>
          <ul className="list-disc pl-5 text-xs text-amber-300 space-y-1">{result.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
        </div>}
        {result.evidence.length === 0 ? <p className="text-xs font-mono border border-dashed border-hermes-bone/25 p-4">No matching corpus evidence returned. Insufficient evidence is not disproof.</p> : <div className="space-y-3">
          <h4 className="font-display text-lg">Retrieved evidence passages</h4>
          {result.evidence.map((evidence, index) => {
            const url = safeHttpUrl(evidence.url);
            return <article key={`${evidence.claim_id}-${index}`} className="border border-hermes-bone/20 bg-hermes-panel-deep p-4 space-y-2">
              <div className="flex flex-wrap gap-2 text-xs font-mono">
                <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/75">{evidence.stance}</span>
                <span>{evidence.domain || 'Domain not supplied'}</span>
                <span>Similarity: {Number.isFinite(evidence.similarity) ? evidence.similarity.toFixed(3) : 'not reported'} (heuristic)</span>
              </div>
              <p className="text-sm text-hermes-bone/75">Matched claim: {evidence.text}</p>
              {evidence.passage ? <blockquote className="border-l-2 border-hermes-red-bright pl-3 text-sm whitespace-pre-wrap">{evidence.passage}</blockquote> : <p className="text-xs text-hermes-bone/55">No source passage supplied by the API.</p>}
              {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs font-mono text-hermes-red-bright inline-flex items-center gap-1 break-all">{evidence.title || url}<ExternalLink className="w-3 h-3 shrink-0" /></a> : <p className="text-xs font-mono text-hermes-bone/55">{evidence.title && `${evidence.title} · `}Source link unavailable (HTTP/HTTPS required).</p>}
              {evidence.passage_source && <p className="text-xs text-hermes-bone/55">Passage source: {evidence.passage_source}{evidence.passage_source === 'extracted_claim' ? ' (extracted claim text, not an article-body quotation)' : ''}</p>}
              <p className="text-xs text-hermes-bone/50">Published: {evidence.published_at || 'not supplied'} · article {evidence.article_id} · claim {evidence.claim_id}</p>
              {evidence.syndication_group && <p className="text-xs text-amber-300">Syndication group: {evidence.syndication_group}. Shared-group passages may not be independent corroboration.</p>}
            </article>;
          })}
        </div>}
      </div>}
    </div>
  );
}

export function ClaimCheck() {
  const { user, revision } = useSession();
  return (
    <section aria-labelledby="claim-check-title" className="card-brutal-dark p-6 space-y-4">
      <h2 id="claim-check-title" className="font-display text-2xl flex items-center gap-2"><FileSearch className="w-5 h-5" /> Corpus Evidence Check</h2>
      <p className="text-sm text-hermes-bone/65">Check a supplied claim against retrieved corpus passages, with source links, model stances and explicit uncertainty. This is not an independent fact verification service.</p>
      {user ? <CheckForm key={revision} /> : <SignInNotice feature="corpus evidence checking" />}
    </section>
  );
}
