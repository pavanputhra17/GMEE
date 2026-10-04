import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardCheck, Scale, GitBranch, Unlink, Download } from 'lucide-react';
import { evalApi, EvalLabel, EvalPair, type EvalStrategy, type EvalSplit } from '../api/eval';
import { useSession } from '../lib/session';
import { usePollingPolicy } from '../lib/polling';
import { downloadApiResponse } from '../lib/download';
import { QueryError } from './QueryError';
import { SignInNotice } from './SignInNotice';

/**
 * EvalLab — authenticated, blinded claim-pair labeling.
 *
 * Serves blinded claim pairs (texts + outlets only; similarity scores are
 * withheld by the backend so annotators judge the claims, not the machine)
 * and records SAME_STORY / EVOLVED / DISTINCT votes. Progress panel shows
 * per-bucket coverage and Cohen's kappa between annotators.
 */

const LABEL_META: Array<{
  label: EvalLabel;
  title: string;
  hint: string;
  icon: React.ElementType;
  cls: string;
  key: string;
}> = [
  {
    label: 'SAME_STORY',
    title: 'Same story',
    hint: 'Same event and facts, paraphrased across outlets',
    icon: Scale,
    cls: 'border-emerald-400/40 bg-emerald-400/5 hover:bg-emerald-400/10 text-emerald-300',
    key: '1',
  },
  {
    label: 'EVOLVED',
    title: 'Evolved',
    hint: 'Same story but facts shifted — numbers, entities or hedging changed',
    icon: GitBranch,
    cls: 'border-amber-300/40 bg-amber-300/5 hover:bg-amber-300/10 text-amber-300',
    key: '2',
  },
  {
    label: 'DISTINCT',
    title: 'Distinct',
    hint: 'Different stories that happen to share words',
    icon: Unlink,
    cls: 'border-hermes-bone/25 bg-hermes-panel-deep hover:bg-hermes-panel text-hermes-bone/80',
    key: '3',
  },
];

const ClaimCard: React.FC<{ side: 'A' | 'B'; text: string; domain: string | null }> = ({
  side,
  text,
  domain,
}) => (
  <div className="border border-hermes-bone/15 bg-hermes-panel-deep p-5 flex flex-col gap-3 flex-1">
    <div className="flex items-center gap-2">
      <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/70 !text-[10px]">
        Claim {side}
      </span>
      <span className="font-mono text-[10px] text-hermes-bone/45 truncate">{domain}</span>
    </div>
    <p className="text-base leading-relaxed text-hermes-bone/90">&ldquo;{text}&rdquo;</p>
  </div>
);

const PairView: React.FC<{
  pair: EvalPair;
  annotator: string;
  onLabeled: (label: EvalLabel) => void;
  pending: boolean;
  justLabeled: EvalLabel | null;
}> = ({ pair, annotator, onLabeled, pending, justLabeled }) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (pending || !annotator) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
      const target = e.target instanceof HTMLElement ? e.target : null;
      if (target?.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')) return;
      const meta = LABEL_META.find((m) => m.key === e.key);
      if (meta) { e.preventDefault(); onLabeled(meta.label); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pending, annotator, onLabeled]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col lg:flex-row gap-4">
        <ClaimCard side="A" text={pair.a.text} domain={pair.a.domain} />
        <ClaimCard side="B" text={pair.b.text} domain={pair.b.domain} />
      </div>

      {justLabeled && (
        <p className="font-mono text-xs text-emerald-300 border border-emerald-400/30 bg-emerald-400/5 p-3">
          Recorded {justLabeled} — fetching the next unlabeled pair…
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {LABEL_META.map((m) => {
          const Icon = m.icon;
          return (
            <button
              key={m.label}
              onClick={() => onLabeled(m.label)}
              disabled={pending}
              className={`border p-4 text-left transition-colors disabled:opacity-50 disabled:cursor-wait cursor-pointer ${m.cls}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-4 h-4" />
                <span className="font-display text-lg">{m.title}</span>
                <kbd className="ml-auto font-mono text-[10px] border border-current/30 px-1.5 py-0.5 opacity-60">
                  {m.key}
                </kbd>
              </div>
              <div className="text-xs opacity-70 leading-snug">{m.hint}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
export const EvalLab: React.FC = () => {
  const queryClient = useQueryClient();
  const { user, revision } = useSession();
  const polling = usePollingPolicy(30000);
  const [strategy, setStrategy] = useState<EvalStrategy>('coverage');
  const [split, setSplit] = useState<EvalSplit>('unassigned');
  const [mutationTypes, setMutationTypes] = useState('');
  const [notes, setNotes] = useState('');
  const [annotationError, setAnnotationError] = useState('');
  const [datasetVersion, setDatasetVersion] = useState('');
  const [publication, setPublication] = useState(false);
  const [justLabeled, setJustLabeled] = useState<EvalLabel | null>(null);

  const nextKey = ['eval', revision, 'next', strategy, split];
  const progressKey = ['eval', revision, 'progress'];
  const next = useQuery({
    queryKey: nextKey,
    queryFn: ({ signal }) => evalApi.next(strategy, split, { signal }),
    enabled: !!user,
    ...polling,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const progress = useQuery({
    queryKey: progressKey,
    queryFn: ({ signal }) => evalApi.progress({ signal }),
    enabled: !!user,
    ...polling,
  });
  const labelMutation = useMutation({
    mutationFn: ({ pairId, label, types, note }: { pairId: string; label: EvalLabel; types: string[]; note: string }) =>
      evalApi.label(pairId, label, { ...(types.length ? { mutation_types: types } : {}), ...(note ? { notes: note } : {}) }),
    onSuccess: async (_data, vars) => {
      setJustLabeled(vars.label);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: nextKey }),
        queryClient.invalidateQueries({ queryKey: progressKey }),
      ]);
    },
  });
  const exportMutation = useMutation({
    mutationFn: () => evalApi.export(datasetVersion.trim(), publication),
    onSuccess: downloadApiResponse,
  });

  const latestPairId = next.data?.pair?.pair_id;
  useEffect(() => {
    setJustLabeled(null);
    setMutationTypes('');
    setNotes('');
    setAnnotationError('');
  }, [latestPairId, revision, strategy, split]);

  const pair = next.data?.pair ?? null;
  const castVote = (label: EvalLabel) => {
    if (!pair || !user || labelMutation.isPending || next.isFetching || justLabeled) return;
    const types = [...new Set(mutationTypes.split(',').map((value) => value.trim()).filter(Boolean))];
    if (types.length > 16 || types.some((type) => type.length > 64)) {
      setAnnotationError('Use at most 16 mutation types, each at most 64 characters.');
      return;
    }
    setAnnotationError('');
    labelMutation.mutate({ pairId: pair.pair_id, label, types, note: notes.trim() });
  };

  return (
    <section className="card-brutal-dark p-6 flex flex-col gap-5">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-hermes-bone/12">
        <div className="flex items-center gap-2"><ClipboardCheck className="w-5 h-5" /><h2 className="text-2xl font-display">Eval Lab</h2></div>
        {user && <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/60">
          {progress.data ? `${progress.data.labeled_pairs_distinct.toLocaleString()} / ${progress.data.total_pairs.toLocaleString()} labeled` : progress.isLoading ? 'Loading coverage…' : 'Coverage unavailable'}
        </span>}
      </div>
      <p className="font-mono text-[11px] leading-relaxed text-hermes-bone/55 border-l-2 border-hermes-bone/25 pl-3">
        Blinded by design: pair scores and engine verdicts are withheld. Judge the claim texts, not the machine. Keys 1 / 2 / 3 vote outside form fields. Agreement does not establish correctness or benchmark validity.
      </p>
      {!user ? <SignInNotice feature="Eval Lab" /> : <>
        <p className="text-xs font-mono">Authenticated annotator: {user.full_name || user.email}. Labels are bound to your account ID by the server.</p>
        <div className="flex flex-wrap gap-4">
          <div><label htmlFor="eval-strategy" className="block text-xs font-mono mb-1">Sampling strategy</label>
            <select id="eval-strategy" value={strategy} disabled={labelMutation.isPending} onChange={(event) => {
              const value = event.target.value as EvalStrategy;
              setStrategy(value);
              if (value === 'uncertainty') setSplit('train');
              labelMutation.reset();
            }} className="field-brutal">
              <option value="coverage">Coverage</option><option value="uncertainty">Uncertainty (train only)</option>
            </select>
          </div>
          <div><label htmlFor="eval-split" className="block text-xs font-mono mb-1">Dataset split</label>
            <select id="eval-split" value={split} disabled={labelMutation.isPending || strategy === 'uncertainty'} onChange={(event) => { setSplit(event.target.value as EvalSplit); labelMutation.reset(); }} className="field-brutal">
              <option value="unassigned">Unassigned</option><option value="train">Train</option><option value="dev">Dev</option><option value="test">Test</option>
            </select>
          </div>
        </div>
        {strategy === 'uncertainty' && <p className="text-xs text-amber-300">Training pairs only: uncertainty is heuristic score proximity, not calibrated probability entropy. Held-out splits retain fixed coverage order.</p>}
        {next.isLoading ? <div role="status" className="space-y-2" data-testid="eval-skeleton"><span className="text-xs font-mono">Loading blinded pair…</span><div className="shimmer h-32" /></div>
          : next.isError ? <QueryError title="Eval pairs unavailable" error={next.error} onRetry={() => next.refetch()} retrying={next.isFetching} />
          : !pair ? <p className="font-mono text-xs border border-dashed border-hermes-bone/25 p-3">
            {next.data?.done ? progress.data?.total_pairs === 0 ? 'No evaluation pairs available. Nothing has been fabricated.' : 'No remaining pairs in the selected split for this account.' : 'The API returned no pair. No completion is inferred.'}
          </p> : <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><label htmlFor="eval-mutation-types" className="block text-xs font-mono mb-1">Mutation types (optional, comma-separated)</label>
                <input id="eval-mutation-types" value={mutationTypes} maxLength={1040} disabled={labelMutation.isPending || !!justLabeled} onChange={(event) => setMutationTypes(event.target.value)} className="field-brutal w-full" />
              </div>
              <div><label htmlFor="eval-notes" className="block text-xs font-mono mb-1">Notes (optional)</label>
                <textarea id="eval-notes" rows={2} maxLength={2000} value={notes} disabled={labelMutation.isPending || !!justLabeled} onChange={(event) => setNotes(event.target.value)} className="field-brutal w-full" />
              </div>
            </div>
            {annotationError && <p role="alert" className="text-xs text-hermes-red-bright">{annotationError}</p>}
            {labelMutation.isError && <QueryError title="Vote failed to record; the pair is preserved" error={labelMutation.error} onRetry={() => { if (labelMutation.variables) labelMutation.mutate(labelMutation.variables); }} retrying={labelMutation.isPending} />}
            <PairView pair={pair} annotator={user.id} onLabeled={castVote} pending={labelMutation.isPending || next.isFetching || !!justLabeled} justLabeled={justLabeled} />
          </>}

        {progress.isLoading && <p role="status" className="text-xs font-mono">Loading evaluation progress…</p>}
        {progress.isError && <><QueryError title="Eval progress unavailable" error={progress.error} onRetry={() => progress.refetch()} retrying={progress.isFetching} />
          {progress.data && <p className="text-xs text-amber-300">Last real progress is shown below; it may be stale.</p>}
        </>}
        {progress.data && <div className="border-t border-hermes-bone/12 pt-4 flex flex-col gap-4">
          <h3 className="font-mono text-xs text-hermes-bone/65">Coverage by similarity bucket</h3>
          {progress.data.by_bucket.length === 0 && <p className="text-xs font-mono text-hermes-bone/55">No evaluation buckets available.</p>}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {progress.data.by_bucket.map((bucket) => <div key={bucket.bucket} className="border border-hermes-bone/12 bg-hermes-panel-deep px-2.5 py-2">
              <div className="font-mono text-[10px] text-hermes-bone/45">{bucket.bucket}</div>
              <div className="text-sm font-display tabular-nums">{bucket.labeled.toLocaleString()}<span className="text-hermes-bone/40"> / {bucket.pairs.toLocaleString()}</span></div>
              <div className="h-1 mt-1.5 bg-hermes-bone/10"><div className="h-full bg-hermes-bone/60" style={{ width: `${bucket.pairs ? Math.min(100, (bucket.labeled / bucket.pairs) * 100) : 0}%` }} /></div>
            </div>)}
          </div>
          <h3 className="font-mono text-xs text-hermes-bone/65">Label origins</h3>
          {progress.data.origins ? <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(progress.data.origins).map(([origin, counts]) => <div key={origin} className="border border-hermes-bone/15 p-3 text-xs font-mono">
              <dt>{origin}</dt><dd>{counts.votes} votes · {counts.pairs} pairs</dd>
            </div>)}
          </dl> : <p className="text-xs text-hermes-bone/55">Label origin breakdown is not reported by this API version.</p>}
          <p className="text-xs text-amber-300">Automatic, legacy and test labels are not independent human gold. Coverage and agreement are descriptive, not a validated benchmark.</p>
          {progress.data.warning && <p role="note" className="text-xs text-amber-300">{progress.data.warning}</p>}
          {progress.data.warnings?.map((warning, index) => <p key={index} role="note" className="text-xs text-amber-300">{warning}</p>)}
          {progress.data.inter_annotator.length > 0 ? <div className="space-y-2">
            {progress.data.inter_annotator.map((agreement) => <div key={agreement.annotators.join('+')} className="text-xs font-mono">
              <p>kappa {agreement.annotators.join(' × ')}: {agreement.kappa == null ? 'not estimable' : agreement.kappa.toFixed(3)} (n={agreement.pairs})</p>
              {agreement.warning && <p className="text-amber-300">{agreement.warning}</p>}
            </div>)}
          </div> : <p className="text-xs text-hermes-bone/55">No inter-annotator agreement returned yet.</p>}
        </div>}
        {user.role.toLowerCase() === 'admin' && <div className="border-t border-hermes-bone/15 pt-4 space-y-3">
          <h3 className="font-display text-xl">Admin dataset export</h3>
          <p className="text-xs text-hermes-bone/60">Downloads the actual /eval/export response, including provenance. No benchmark records or charts are generated in the browser.</p>
          <label htmlFor="eval-dataset-version" className="block text-xs font-mono">Dataset version</label>
          <input id="eval-dataset-version" maxLength={128} value={datasetVersion} disabled={exportMutation.isPending} onChange={(event) => { setDatasetVersion(event.target.value); exportMutation.reset(); }} className="field-brutal w-full" />
          <label className="flex items-center gap-2 text-xs font-mono"><input type="checkbox" checked={publication} disabled={exportMutation.isPending} onChange={(event) => setPublication(event.target.checked)} /> Publication mode (human-only; server validates eligibility)</label>
          <button type="button" disabled={exportMutation.isPending || !datasetVersion.trim()} onClick={() => exportMutation.mutate()} className="btn-brutal"><Download className="w-3.5 h-3.5" /> {exportMutation.isPending ? 'Downloading export…' : 'Download actual export'}</button>
          {exportMutation.isError && <QueryError title="Eval export unavailable" error={exportMutation.error} onRetry={() => exportMutation.mutate()} retrying={exportMutation.isPending} />}
          {exportMutation.isSuccess && <p role="status" className="text-xs font-mono">Export response downloaded.</p>}
        </div>}
      </>}
    </section>
  );
};

