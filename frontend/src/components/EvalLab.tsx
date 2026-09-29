import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardCheck, Scale, GitBranch, Unlink, ChevronRight } from 'lucide-react';
import { evalApi, EvalLabel, EvalPair } from '../api/eval';

/**
 * EvalLab — the gold-standard labeling workbench.
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

const ClaimCard: React.FC<{ side: 'A' | 'B'; text: string; domain: string }> = ({
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
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      const meta = LABEL_META.find((m) => m.key === e.key);
      if (meta) onLabeled(meta.label);
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
  const [annotator, setAnnotator] = useState<string>(() => evalApi.loadAnnotator());
  const [draft, setDraft] = useState<string>(() => evalApi.loadAnnotator());
  const [justLabeled, setJustLabeled] = useState<EvalLabel | null>(null);

  const name = annotator.trim();
  const next = useQuery({
    queryKey: ['eval', 'next', name],
    queryFn: () => evalApi.next(name),
    enabled: name.length > 0,
  });
  const progress = useQuery({
    queryKey: ['eval', 'progress'],
    queryFn: () => evalApi.progress(),
    refetchInterval: 30000,
  });
  const labelMutation = useMutation({
    mutationFn: ({ pairId, label }: { pairId: string; label: EvalLabel }) =>
      evalApi.label(pairId, name, label),
    onSuccess: (_data, vars) => {
      setJustLabeled(vars.label);
      queryClient.invalidateQueries({ queryKey: ['eval', 'next', name] });
      queryClient.invalidateQueries({ queryKey: ['eval', 'progress'] });
    },
  });

  const latestPairId = next.data?.pair?.pair_id;
  useEffect(() => {
    if (latestPairId) setJustLabeled(null);
  }, [latestPairId]);

  const claimName = () => {
    const v = draft.trim();
    if (!v) return;
    setAnnotator(v);
    evalApi.saveAnnotator(v);
  };

  const labeled = progress.data?.labeled_pairs_distinct ?? 0;
  const total = progress.data?.total_pairs ?? 0;
  const pair = next.data?.pair ?? null;
  const castVote = (label: EvalLabel) => {
    if (pair) labelMutation.mutate({ pairId: pair.pair_id, label });
  };

  return (
    <section className="card-brutal-dark p-6 flex flex-col gap-5">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-hermes-bone/12">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="w-5 h-5" />
          <h2 className="text-2xl font-display">Eval Lab</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/60">
            {total > 0 ? `${labeled.toLocaleString()} / ${total.toLocaleString()} labeled` : 'coverage —'}
          </span>
          {progress.data && progress.data.inter_annotator.length > 0 && (
            <span className="chip-brutal border-emerald-400/40 text-emerald-300">
              kappa {progress.data.inter_annotator[0].kappa.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      <p className="font-mono text-[11px] leading-relaxed text-hermes-bone/50 border-l-2 border-hermes-bone/25 pl-3">
        Blinded by design: the backend withholds similarity scores, buckets and engine
        verdicts — judge only the two claim texts. Keys 1 / 2 / 3 vote.
      </p>

      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <label htmlFor="eval-annotator" className="font-mono text-[11px] uppercase tracking-widest text-hermes-bone/55 shrink-0">
          Annotator
        </label>
        <input
          id="eval-annotator"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && claimName()}
          placeholder="your handle, e.g. pavan"
          maxLength={64}
          className="bg-hermes-panel-deep border border-hermes-bone/25 px-3 py-2 text-sm font-mono text-hermes-bone placeholder:text-hermes-bone/30 outline-none focus:border-hermes-bone/60 flex-1"
        />
        <button onClick={claimName} className="btn-brutal !py-2 flex items-center gap-1">
          {name ? 'Switch' : 'Start'} <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {!name ? (
        <p className="font-mono text-xs text-hermes-bone/50 border border-dashed border-hermes-bone/20 p-3">
          Enter an annotator handle to pull your first blinded pair.
        </p>
      ) : next.isLoading ? (
        <div className="space-y-2" data-testid="eval-skeleton">
          <div className="shimmer h-32" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="shimmer h-24" />
            ))}
          </div>
        </div>
      ) : next.isError ? (
        <p className="font-mono text-xs text-hermes-bone/50 border border-dashed border-hermes-bone/20 p-3">
          Eval backend unreachable — labeling resumes as soon as the API answers. No
          pairs are fabricated.
        </p>
      ) : !pair ? (
        <p className="font-mono text-xs text-emerald-300 border border-emerald-400/30 bg-emerald-400/5 p-3">
          Done — you have labeled every pair in the gold set{name ? `, ${name}` : ''}.
        </p>
      ) : labelMutation.isError ? (
        <div className="flex flex-col gap-4">
          <p className="font-mono text-xs text-hermes-red-bright border border-hermes-red-bright/40 bg-hermes-red-bright/5 p-3">
            Vote failed to record — the backend rejected it. Your pair is preserved below;
            retry once the API recovers.
          </p>
          <PairView
            pair={pair}
            annotator={name}
            onLabeled={castVote}
            pending={labelMutation.isPending}
            justLabeled={null}
          />
        </div>
      ) : (
        <PairView
          pair={pair}
          annotator={name}
          onLabeled={castVote}
          pending={labelMutation.isPending}
          justLabeled={justLabeled}
        />
      )}

      {progress.data && (
        <div className="border-t border-hermes-bone/12 pt-4 flex flex-col gap-3">
          <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45">
            Coverage by similarity bucket
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
            {progress.data.by_bucket.map((b) => (
              <div key={b.bucket} className="border border-hermes-bone/12 bg-hermes-panel-deep px-2.5 py-2">
                <div className="font-mono text-[10px] text-hermes-bone/45">{b.bucket}</div>
                <div className="text-sm font-display tabular-nums">
                  {b.labeled.toLocaleString()}
                  <span className="text-hermes-bone/40"> / {b.pairs.toLocaleString()}</span>
                </div>
                <div className="h-1 mt-1.5 bg-hermes-bone/10">
                  <div
                    className="h-full bg-hermes-bone/60"
                    style={{ width: `${b.pairs ? Math.min(100, (b.labeled / b.pairs) * 100) : 0}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          {progress.data.inter_annotator.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {progress.data.inter_annotator.map((k) => (
                <span key={k.annotators.join('+')} className="chip-brutal border-hermes-bone/25 text-hermes-bone/60">
                  kappa {k.annotators.join(' x ')}: {k.kappa.toFixed(3)} (n={k.pairs})
                </span>
              ))}
            </div>
          ) : (
            <p className="font-mono text-[10px] text-hermes-bone/40">
              No kappa yet — two annotators need at least 5 shared pairs before agreement is meaningful.
            </p>
          )}
        </div>
      )}
    </section>
  );
};

