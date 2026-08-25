import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Radio, ExternalLink } from 'lucide-react';
import { corpusApi } from '../api/corpus';

/**
 * LiveAuditFeed — the REAL ingest stream: newest collected articles from
 * Postgres, refreshed on a calm cadence. No synthetic rows.
 */

export const LiveAuditFeed: React.FC = () => {
  const recent = useQuery({
    queryKey: ['ingest-stream'],
    queryFn: () => corpusApi.recent(14),
    refetchInterval: 20000,
  });

  return (
    <div className="card-brutal-dark p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between pb-3 border-b border-hermes-bone/12">
        <div className="flex items-center gap-2">
          <Radio className="w-5 h-5" />
          <h2 className="text-2xl font-display">Live Ingest Stream</h2>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-emerald-400">|</span>
          <span className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/55">
            newest collections · postgres
          </span>
        </div>
      </div>

      <div className="border border-hermes-bone/20">
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-hermes-panel-deep border-b border-hermes-bone/20">
          <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F56]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#FFBB2E]" />
          <span className="w-2.5 h-2.5 rounded-full bg-[#27C93F]" />
          <span className="ml-2 text-[10px] font-mono uppercase tracking-widest text-hermes-red-bright">
            gmee://corpus-ingest
          </span>
        </div>

        <div className="bg-hermes-panel-deep p-3 font-mono text-xs max-h-72 overflow-y-auto space-y-0.5">
          {recent.isLoading && [...Array(8)].map((_, i) => (
            <div key={i} className="shimmer h-7 mb-1" />
          ))}

          {recent.isError && (
            <div className="text-hermes-red-bright p-2">stream unavailable</div>
          )}

          {recent.data?.items.map((r, index) => (
            <a
              key={r.id}
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className={`group flex items-start gap-3 px-1.5 py-1.5 hover:bg-hermes-panel transition-colors border-l-2 border-l-transparent ${
                r.domain === 'www.thehindu.com' ? 'border-l-hermes-red' : ''
              } ${index === 0 ? 'feed-enter' : ''}`}
            >
              <span className="mt-0.5 w-1.5 h-1.5 shrink-0 bg-hermes-red-bright" />
              <span className="text-hermes-bone/40 whitespace-nowrap text-[11px] tabular-nums shrink-0">
                {r.collected_at
                  ? new Date(r.collected_at).toLocaleTimeString('en-US', { hour12: false })
                  : '—'}
              </span>
              <span className="px-1 py-0.5 text-[9px] font-bold uppercase tracking-wider bg-white text-hermes-red-deep border border-hermes-red-deep/50 whitespace-nowrap h-fit shrink-0 max-w-[110px] truncate">
                {(r.source_name || r.domain || 'web').replace(/^(www|rss)\./, '')}
              </span>
              <span className="text-hermes-bone/80 flex-1 leading-relaxed group-hover:text-white min-w-0">
                <span className="line-clamp-1">{r.title}</span>
              </span>
              <ExternalLink className="w-3 h-3 mt-0.5 shrink-0 opacity-0 group-hover:opacity-60" />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
};
