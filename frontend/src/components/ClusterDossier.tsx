import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { TimelineCluster } from '../api/timeline';

/**
 * ClusterDossier — the inspector modal behind the timeline tunnel.
 *
 * Rich but honest: every number on display is real data from
 * `/graph/timeline` — similarity meters, publish-time lag versus the hub
 * (or a "scoop" badge when the member beat the hub to the story), coverage
 * span and the similarity range across the cluster.
 */

const OUTLET_COLORS: Record<string, string> = {
  'www.thehindu.com': '#E11D2E',
  'www.aljazeera.com': '#FF8A5C',
  'www.theguardian.com': '#7FB4FF',
  'www.ndtv.com': '#9BE38A',
  'timesofindia.indiatimes.com': '#E3C567',
  'www.bbc.co.uk': '#C99CFF',
  'www.wired.com': '#6FE0D2',
  'www.nytimes.com': '#F2F2F2',
  'techcrunch.com': '#8FD18F',
  'www.npr.org': '#FFB3C7',
  'news.sky.com': '#79A8FF',
  'theverge.com': '#FF7AC8',
  'www.cnn.com': '#FF6B6B',
};

const colorFor = (d?: string | null): string => (d && OUTLET_COLORS[d]) || '#B08A85';

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';

const fmtDur = (ms: number): string => {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
};

const Chip: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="chip-brutal border-hermes-bone/15 text-hermes-bone/55 !text-[9px] !px-1.5 !py-0.5">
    {children}
  </span>
);

export const ClusterDossier: React.FC<{
  cluster: TimelineCluster;
  isFocused: boolean;
  onClose: () => void;
}> = ({ cluster, isFocused, onClose }) => {
  const parsed = [cluster.published_at, ...cluster.members.map((m) => m.published_at)]
    .filter((t): t is string => !!t)
    .map((t) => Date.parse(t))
    .filter((n) => !Number.isNaN(n));
  const first = parsed.length ? Math.min(...parsed) : null;
  const last = parsed.length ? Math.max(...parsed) : null;
  const scores = cluster.members.map((m) => m.score);
  const lo = scores.length ? Math.min(...scores) : null;
  const hi = scores.length ? Math.max(...scores) : null;
  const hubAt = cluster.published_at ? Date.parse(cluster.published_at) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="max-w-xl w-full border border-hermes-bone/25 bg-hermes-panel shadow-[6px_6px_0_0_rgba(0,0,0,0.65)] flex flex-col max-h-[85vh]"
        onClick={(ev) => ev.stopPropagation()}
      >
        {/* brutalist accent strip */}
        <div className="h-1 bg-hermes-red shrink-0" />

        <div className="p-6 flex flex-col gap-4 overflow-y-auto scroll-contained">
          <div className="flex items-start justify-between gap-4 pb-3 border-b border-hermes-bone/15">
            <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45">
              Cluster dossier · {cluster.members.length + 1} articles
            </div>
            <button
              onClick={onClose}
              aria-label="Close dossier"
              className="btn-ghost-brutal !py-0.5 !px-2 !text-hermes-bone !border-hermes-bone/30"
            >
              ×
            </button>
          </div>

          {/* hub head */}
          <div>
            <div className="flex items-start gap-2 mb-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0 mt-2"
                style={{ background: colorFor(cluster.domain) }}
              />
              <a href={cluster.url ?? '#'} target="_blank" rel="noreferrer" className="group min-w-0">
                <h3 className="font-display text-lg leading-snug text-white group-hover:text-hermes-red-bright transition-colors">
                  {cluster.title}
                </h3>
              </a>
            </div>
            <div className="flex items-center gap-2 flex-wrap font-mono text-[10px] uppercase tracking-wider text-hermes-bone/45">
              <span>{fmtDate(cluster.published_at)}</span>
              <span className="text-hermes-bone/25">·</span>
              <span style={{ color: colorFor(cluster.domain) }}>
                {cluster.domain?.replace('www.', '')}
              </span>
              <span className="chip-brutal bg-hermes-red-bright text-white border-hermes-red-bright !text-[9px] !px-1.5 !py-0.5">
                hub
              </span>
              {isFocused && (
                <span className="chip-brutal border-emerald-400/50 bg-emerald-400/10 text-emerald-300 !text-[9px] !px-1.5 !py-0.5">
                  your selection
                </span>
              )}
            </div>
            {first !== null && last !== null && (
              <div className="font-mono text-[10px] text-hermes-bone/40 mt-1.5">
                first reported {fmtDate(new Date(first).toISOString())} · coverage span{' '}
                {fmtDur(last - first)}
              </div>
            )}
          </div>
          {/* members */}
          <div className="space-y-1.5">
            {cluster.members.map((m) => {
              const at = m.published_at ? Date.parse(m.published_at) : null;
              const lag = at !== null && hubAt !== null ? at - hubAt : null;
              return (
                <a
                  key={m.id}
                  href={m.url ?? '#'}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-center gap-3 border border-hermes-bone/10 bg-hermes-panel-deep px-3 py-2 hover:border-hermes-bone/30 transition-colors"
                >
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: colorFor(m.domain) }}
                  />
                  {/* similarity meter */}
                  <div className="w-14 shrink-0 flex flex-col items-end gap-1">
                    <span className="font-mono text-xs tabular-nums text-hermes-red-bright leading-none">
                      {(m.score * 100).toFixed(0)}
                    </span>
                    <span className="h-[3px] w-full bg-hermes-bone/10">
                      <span
                        className="block h-full bg-hermes-red-bright/80"
                        style={{ width: `${Math.round(m.score * 100)}%` }}
                      />
                    </span>
                  </div>
                  <span className="font-mono text-[10px] uppercase text-hermes-bone/40 w-28 truncate shrink-0 hidden sm:block">
                    {m.domain?.replace('www.', '')}
                  </span>
                  <span className="text-xs text-hermes-bone/80 truncate min-w-0 flex-1">
                    {m.title}
                  </span>
                  {lag !== null && (
                    <span className="hidden md:block shrink-0">
                      <Chip>
                        {lag >= 0 ? `+${fmtDur(lag)} later` : `scoop ${fmtDur(-lag)} before`}
                      </Chip>
                    </span>
                  )}
                  <ExternalLink className="w-3 h-3 shrink-0 text-hermes-bone/30 group-hover:text-hermes-red-bright" />
                </a>
              );
            })}
          </div>

          {/* footer stats */}
          <div className="flex items-center gap-2 flex-wrap pt-3 border-t border-hermes-bone/10">
            {hi !== null && (
              <Chip>
                match{' '}
                {lo !== null
                  ? `${(lo * 100).toFixed(0)}–${(hi * 100).toFixed(0)}%`
                  : `${(hi * 100).toFixed(0)}%`}
              </Chip>
            )}
            {last !== null && (
              <Chip>newest coverage {fmtDate(new Date(last).toISOString())}</Chip>
            )}
            <Chip>{cluster.deg} similarity links</Chip>
          </div>
        </div>
      </div>
    </div>
  );
};
