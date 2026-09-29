import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, BellRing, Siren } from 'lucide-react';
import { alertsApi } from '../api/alerts';

/**
 * Early warning board — persisted alert rows (deduplicated in the `alerts`
 * table by the backend evaluator) plus the stateless 24h spike snapshot.
 * Real data only: no synthetic rows, no demo drift.
 */

const SEVERITY_STYLE: Record<string, { cls: string; icon: React.ElementType }> = {
  CRITICAL: {
    cls: 'text-hermes-red-bright border-hermes-red-bright/50 bg-hermes-red-bright/10',
    icon: Siren
  },
  WARNING: {
    cls: 'text-amber-300 border-amber-300/40 bg-amber-300/5',
    icon: AlertTriangle
  },
  INFO: {
    cls: 'text-hermes-bone/70 border-hermes-bone/25 bg-hermes-panel-deep',
    icon: BellRing
  }
};

const KIND_LABEL: Record<string, string> = {
  CONTRADICTION: 'cross-outlet contradiction',
  CORROBORATION: 'independent corroboration',
  MUTATION: 'claim mutation',
  SPIKE: 'story burst',
  INGESTION_SPIKE: 'collection surge',
  DISPUTED_SURGE: 'disputed surge',
  MUTATION_SURGE: 'mutation surge'
};

const when = (iso: string | null): string => {
  if (!iso) return 'unknown';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'unknown';
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
};

const Stat: React.FC<{ label: string; value: number; prior: number }> = ({
  label,
  value,
  prior
}) => (
  <div className="border border-hermes-bone/12 bg-hermes-panel-deep px-3 py-2">
    <div className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45">
      {label}
    </div>
    <div className="text-lg font-display tabular-nums leading-tight">
      {value.toLocaleString()}
      <span className="ml-2 text-[10px] font-mono text-hermes-bone/40">
        prev {prior.toLocaleString()}
      </span>
    </div>
  </div>
);

export const EarlyWarning: React.FC = () => {
  const snapshot = useQuery({
    queryKey: ['alerts', 'snapshot'],
    queryFn: () => alertsApi.snapshot(),
    refetchInterval: 60000
  });

  const feed = useQuery({
    queryKey: ['alerts', 'feed'],
    queryFn: () => alertsApi.feed(12),
    refetchInterval: 60000
  });

  const items = feed.data?.items ?? [];
  const signals = (snapshot.data?.alerts ?? []).filter((s) => s.type !== 'QUIET');
  const quiet =
    snapshot.data !== undefined && signals.length === 0 && items.length === 0;
  const stats = snapshot.data?.stats;
  const counts = feed.data?.counts;
  const loading = snapshot.isLoading || feed.isLoading;
  const unreachable = !loading && snapshot.isError && feed.isError;

  return (
    <section className="card-brutal-dark p-6 flex flex-col gap-5">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-hermes-bone/12">
        <div className="flex items-center gap-2">
          <Siren className="w-5 h-5" />
          <h2 className="text-2xl font-display">Early Warning</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/60">
            {counts ? `${counts.unacknowledged} open` : 'open —'}
          </span>
          {counts && (counts.by_severity.CRITICAL ?? 0) > 0 && (
            <span className="chip-brutal border-hermes-red-bright/50 text-hermes-red-bright">
              {counts.by_severity.CRITICAL} critical
            </span>
          )}
          <span className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45">
            alerts table · deduplicated
          </span>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Stat label="Articles · 24h" value={stats.articles_24h} prior={stats.articles_prior_24h} />
          <Stat label="Disputed · 24h" value={stats.disputed_24h} prior={stats.disputed_prior_24h} />
          <Stat label="Mutations · 24h" value={stats.mutations_24h} prior={stats.mutations_prior_24h} />
        </div>
      )}

      {loading ? (
        <div className="space-y-2" data-testid="alerts-skeleton">
          {[0, 1, 2].map((i) => (
            <div key={i} className="shimmer h-14" />
          ))}
        </div>
      ) : unreachable ? (
        <p className="font-mono text-xs text-hermes-bone/50 border border-dashed border-hermes-bone/20 p-3">
          Alert engine unreachable — the feed resumes as soon as the backend
          answers. No simulated alerts are shown.
        </p>
      ) : quiet ? (
        <p className="font-mono text-xs text-hermes-bone/50 border border-dashed border-hermes-bone/20 p-3">
          All quiet — no anomalous collection, verdict or mutation activity in the
          last 24h.
        </p>
      ) : (
        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {items.map((a) => {
            const style = SEVERITY_STYLE[a.severity] ?? SEVERITY_STYLE.INFO;
            const Icon = style.icon;
            return (
              <article
                key={a.id}
                className="border border-hermes-bone/12 bg-hermes-panel-deep px-3 py-2.5"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`chip-brutal !text-[10px] flex items-center gap-1 ${style.cls}`}>
                    <Icon className="w-3 h-3" />
                    {a.severity}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-hermes-bone/45">
                    {KIND_LABEL[a.kind] ?? a.kind.toLowerCase()}
                  </span>
                  <span className="ml-auto font-mono text-[10px] text-hermes-bone/40 tabular-nums">
                    {when(a.last_seen_at)}
                  </span>
                </div>
                <div className="text-sm text-hermes-bone/90 leading-snug">{a.title}</div>
                {a.body && (
                  <div className="text-xs text-hermes-bone/55 mt-1 line-clamp-2">{a.body}</div>
                )}
              </article>
            );
          })}

          {signals.map((s) => {
            const style =
              SEVERITY_STYLE[s.severity.toUpperCase()] ?? SEVERITY_STYLE.INFO;
            return (
              <article
                key={s.type}
                className="border border-hermes-bone/12 bg-hermes-panel px-3 py-2.5"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className={`chip-brutal !text-[10px] ${style.cls}`}>
                    {s.severity.toUpperCase()}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-hermes-bone/45">
                    24h snapshot
                  </span>
                </div>
                <div className="text-sm text-hermes-bone/90 leading-snug">{s.title}</div>
                <div className="text-xs text-hermes-bone/55 mt-1">{s.detail}</div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
};
