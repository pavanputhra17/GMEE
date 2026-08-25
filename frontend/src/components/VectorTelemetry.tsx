import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Database, Search, ExternalLink, Zap } from 'lucide-react';
import { corpusApi, CorpusStats } from '../api/corpus';

/**
 * VectorTelemetry — REAL corpus stats + working semantic search.
 * Stats read from /corpus/stats (Postgres truth). The search box embeds the
 * query and runs pgvector nearest-neighbor over article embeddings.
 */

export const VectorTelemetry: React.FC = () => {
  const [q, setQ] = useState('');
  const [submitted, setSubmitted] = useState('');

  const stats = useQuery({
    queryKey: ['corpus-stats'],
    queryFn: () => corpusApi.stats() as Promise<CorpusStats>,
    refetchInterval: 15000,
  });

  const results = useQuery({
    queryKey: ['semantic-search', submitted],
    queryFn: () => corpusApi.search(submitted, 8),
    enabled: submitted.length >= 2,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(q.trim());
  };

  return (
    <div className="card-brutal-dark p-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-hermes-bone/12">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Database className="w-5 h-5" />
            <h2 className="text-2xl font-display">Semantic Corpus Search</h2>
          </div>
          <p className="text-xs font-mono text-hermes-bone/55 uppercase tracking-wider">
            pgvector · all-mpnet-base-v2 · {stats.data?.embedded.toLocaleString() ?? '…'} embedded
          </p>
        </div>
        {stats.data && (
          <span className="chip-brutal bg-hermes-panel-deep text-hermes-bone/70 border-hermes-bone/25 w-fit">
            corpus {stats.data.earliest} → {stats.data.latest}
          </span>
        )}
      </div>

      {/* Real stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Articles', value: stats.data?.total.toLocaleString() ?? '—' },
          { label: 'Embedded', value: stats.data?.embedded.toLocaleString() ?? '—' },
          { label: 'Outlets', value: String(stats.data?.domains ?? '—') },
          {
            label: 'NLP pending',
            value:
              stats.data?.nlp_counts?.pending !== undefined
                ? stats.data.nlp_counts.pending.toLocaleString()
                : '—',
          },
        ].map((s) => (
          <div
            key={s.label}
            className="border border-hermes-bone/15 bg-hermes-panel p-4 flex flex-col justify-between"
          >
            <span className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/50">
              {s.label}
            </span>
            <div className="text-xl font-display tabular-nums mt-1">{s.value}</div>
          </div>
        ))}
      </div>

      {/* Semantic search */}
      <form onSubmit={submit} className="flex items-stretch gap-2">
        <div className="flex flex-1 items-center border border-hermes-bone/25 bg-hermes-panel-deep px-3">
          <Search className="w-4 h-4 text-hermes-bone/40 mr-2" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder='try "earthquake deaths" or "AI regulation"…'
            className="flex-1 bg-transparent text-hermes-bone font-mono text-xs py-2.5 outline-none placeholder:text-hermes-bone/35"
          />
        </div>
        <button type="submit" disabled={q.trim().length < 2} className="btn-brutal">
          <Zap className="w-3.5 h-3.5" /> Embed &amp; Match
        </button>
      </form>

      {/* Results */}
      {submitted.length >= 2 && (
        <div className="border border-hermes-bone/20 bg-hermes-panel-deep p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45 mb-3">
            nearest neighbors for “{submitted}” · cosine similarity
          </div>

          {results.isFetching ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="shimmer h-10" />
              ))}
            </div>
          ) : results.isError ? (
            <p className="font-mono text-xs text-hermes-red-bright">
              Search failed — embeddings may still be backfilling.
            </p>
          ) : (
            <div className="divide-y divide-hermes-bone/8">
              {results.data?.items.length === 0 && (
                <p className="font-mono text-xs text-hermes-bone/50 py-2">
                  No embeddings yet — run scripts/embed_articles.py first.
                </p>
              )}
              {results.data?.items.map((r) => (
                <a
                  key={r.id}
                  href={r.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-center gap-3 py-2"
                >
                  <span className="w-12 shrink-0 text-right font-mono text-sm tabular-nums text-hermes-red-bright font-bold">
                    {(r.score * 100).toFixed(1)}
                  </span>
                  <span className="w-28 shrink-0 truncate font-mono text-[10px] uppercase tracking-wider text-hermes-bone/45">
                    {r.domain?.replace('www.', '')}
                  </span>
                  <span className="flex-1 truncate text-xs text-hermes-bone/85 group-hover:text-white">
                    {r.title}
                  </span>
                  <ExternalLink className="w-3 h-3 shrink-0 text-hermes-bone/30 group-hover:text-hermes-red-bright" />
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
