import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ShieldCheck,
  Scale,
  AlertOctagon,
  HelpCircle,
  Trophy,
  ChevronDown,
  ExternalLink,
  FileSearch,
  Landmark,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { extrasApi } from '../api/extras';
import { usePollingPolicy } from '../lib/polling';
import { safeHttpUrl } from '../lib/urls';
import { Dialog } from './Dialog';
import { QueryError } from './QueryError';
import { ClaimCheck } from './ClaimCheck';

/**
 * FactCheck — the Verdict Engine surface.
 * Stored support scores are heuristic and unvalidated, with their evidence
 * chain on display. They are not calibrated probabilities of truth.
 * Nothing is hidden: weights, signals, NLI stances, outlet priors.
 */

export interface VerdictRow {
  id: string;
  claim_text: string;
  verdict: string;
  probability: number | null;
  extraction_confidence: number | null;
  outlet: string;
  article_title: string;
  article_url: string;
}

interface Evidence {
  checked_neighbors?: Array<{ domain: string; similarity: number; stance: string; claim: string }>;
  [key: string]: unknown;
}

interface EvidenceSignal { value: number; weight: number }
function isSignal(value: unknown): value is EvidenceSignal {
  return !!value && typeof value === 'object' && 'value' in value && 'weight' in value
    && typeof value.value === 'number' && Number.isFinite(value.value)
    && typeof value.weight === 'number' && Number.isFinite(value.weight);
}

interface VerdictDetail extends VerdictRow {
  verdict_rationale?: string;
  verdict_evidence?: Evidence | null;
  entities?: Array<{ text: string; type: string }>;
}

const BAND_STYLE: Record<string, { icon: React.ElementType; cls: string; label: string }> = {
  SUPPORTED: { icon: ShieldCheck, cls: 'text-emerald-400 border-emerald-400/40 bg-emerald-400/5', label: 'SUPPORTED' },
  PARTIALLY_SUPPORTED: { icon: ShieldCheck, cls: 'text-teal-300 border-teal-300/40 bg-teal-300/5', label: 'PARTIALLY SUPPORTED' },
  WEAKLY_CORROBORATED: { icon: Scale, cls: 'text-sky-300 border-sky-300/40 bg-sky-300/5', label: 'WEAKLY CORROBORATED' },
  UNRESOLVED: { icon: HelpCircle, cls: 'text-amber-300 border-amber-300/40 bg-amber-300/5', label: 'UNRESOLVED' },
  UNSUPPORTED: { icon: FileSearch, cls: 'text-orange-300 border-orange-300/40 bg-orange-300/5', label: 'UNSUPPORTED · SINGLE SOURCE' },
  DISPUTED: { icon: AlertOctagon, cls: 'text-hermes-red-bright border-hermes-red-bright/50 bg-hermes-red-bright/10', label: 'DISPUTED' },
};

const probColor = (p: number): string =>
  p >= 0.72 ? '#4ade80' : p >= 0.55 ? '#5eead4' : p >= 0.38 ? '#fcd34d' : '#E11D2E';

const VerdictCard: React.FC<{ row: VerdictRow; onOpen: () => void }> = ({ row, onOpen }) => {
  const band = BAND_STYLE[row.verdict] ?? BAND_STYLE.UNRESOLVED;
  const Icon = band.icon;
  const p = row.probability;

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Inspect evidence for ${row.claim_text}`}
      className="w-full text-left border border-hermes-bone/15 bg-hermes-panel-deep p-4 flex flex-col gap-3 cursor-pointer hover:border-hermes-bone/35 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <span className={`chip-brutal w-fit ${band.cls} font-bold`}>
          <Icon className="w-3.5 h-3.5 inline mr-1" />
          {band.label}
        </span>
        <div className="text-right shrink-0">
          <div className="font-display text-xl tabular-nums" style={{ color: p == null ? undefined : probColor(p) }}>
            {p == null ? 'Not scored' : `${(p * 100).toFixed(1)}%`}
          </div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-hermes-bone/40">Heuristic support · unvalidated</div>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-hermes-bone/90 line-clamp-2">{row.claim_text}</p>

      <div className="h-1.5 bg-hermes-bone/10 overflow-hidden">
        <div
          className="h-full transition-all duration-700"
          style={{ width: `${p == null ? 0 : Math.max(0, Math.min(100, p * 100))}%`, background: p == null ? undefined : probColor(p) }}
        />
      </div>

      <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-hermes-bone/45">
        <span className="text-hermes-red-bright/80">{row.outlet?.replace('www.', '')}</span>
        <span className="flex items-center gap-1">
          evidence chain <ChevronDown className="w-3 h-3" />
        </span>
      </div>
    </button>
  );
};

const FeedbackButtons: React.FC<{ claimId: string; engineBand: string }> = ({
  claimId,
  engineBand,
}) => {
  const [status, setStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
  const [corrected, setCorrected] = useState('');

  const send = async (vote: 'AGREE' | 'DISAGREE') => {
    setStatus('sending');
    try {
      await extrasApi.feedback(claimId, vote, vote === 'DISAGREE' && corrected ? corrected : null);
      setStatus('done');
    } catch {
      setStatus('error');
    }
  };

  if (status === 'done') {
    return (
      <div className="border border-emerald-400/30 bg-emerald-400/5 p-4 font-mono text-[10px] uppercase tracking-widest text-emerald-400">
        Vote recorded — anonymous, unverified feedback; not independent validation
      </div>
    );
  }

  return (
    <div className="border border-hermes-bone/15 bg-hermes-panel-deep p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-2">
        Anonymous review · shared IPs may share a vote; not verified human gold
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => void send('AGREE')}
          disabled={status === 'sending'}
          className="btn-ghost-brutal !text-emerald-300 !border-emerald-400/40"
        >
          <ShieldCheck className="w-3.5 h-3.5 inline mr-1" />
          Agree with engine
        </button>
        <button
          onClick={() => void send('DISAGREE')}
          disabled={status === 'sending'}
          className="btn-ghost-brutal !text-hermes-red-bright !border-hermes-red-bright/40"
        >
          <AlertOctagon className="w-3.5 h-3.5 inline mr-1" />
          Disagree with engine
        </button>
        <select
          aria-label="Suggested stored verdict band"
          value={corrected}
          onChange={(e) => setCorrected(e.target.value)}
          className="bg-ink border border-hermes-bone/20 font-mono text-[10px] px-2 py-1.5 text-hermes-bone/80"
        >
          <option value="">if disagree: correct band…</option>
          {Object.keys(BAND_STYLE)
            .filter((b) => b !== engineBand)
            .map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
        </select>
        {status === 'error' && (
          <span className="font-mono text-[10px] text-hermes-red-bright">failed — try again</span>
        )}
      </div>
    </div>
  );
};

const EvidenceDrawer: React.FC<{ detail: VerdictDetail; onClose: () => void }> = ({ detail, onClose }) => {
  const ev = detail.verdict_evidence && typeof detail.verdict_evidence === 'object' ? detail.verdict_evidence : {};
  const neighbors = Array.isArray(ev.checked_neighbors) ? ev.checked_neighbors : [];
  const signals = Object.entries(ev).flatMap(([key, value]) => isSignal(value) ? [{ key, ...value }] : []);

  const SIGNAL_LABELS: Record<string, string> = {
    corroboration: 'Independent corroboration',
    contradiction: 'Cross-outlet contradiction',
    source_track_record: "Source outlet track record",
    entity_grounding: 'Named-entity grounding',
    language: 'Linguistic markers',
  };

  return (
    <Dialog
      labelledBy="verdict-dossier-title"
      onClose={onClose}
      backdropClassName="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
      className="w-full max-w-2xl h-full overflow-y-auto scroll-contained bg-hermes-panel border-l border-hermes-bone/20 p-6 space-y-6"
    >
        {/* header */}
        <div className="flex items-start justify-between gap-4 pb-4 border-b border-hermes-bone/15">
          <div>
            <h2 id="verdict-dossier-title" className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-1">
              Verdict Dossier · stored heuristic analysis
            </h2>
            <span className={`chip-brutal ${(BAND_STYLE[detail.verdict] ?? BAND_STYLE.UNRESOLVED).cls} font-bold`}>
              {(BAND_STYLE[detail.verdict] ?? BAND_STYLE.UNRESOLVED).label} · {detail.probability == null ? 'Not scored' : `${(detail.probability * 100).toFixed(1)}% heuristic support (unvalidated)`}
            </span>
          </div>
          <button onClick={onClose} aria-label="Close verdict dossier" className="btn-ghost-brutal !text-hermes-bone !border-hermes-bone/30 !py-1 !px-2">×</button>
        </div>

        {/* the claim */}
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-1.5">The Claim</div>
          <p className="font-display text-lg leading-snug">{detail.claim_text}</p>
          <a href={safeHttpUrl(detail.article_url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 mt-2 font-mono text-xs text-hermes-red-bright hover:text-white">
            {detail.article_title?.slice(0, 70)}… <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        {/* human feedback */}
        <FeedbackButtons claimId={detail.id} engineBand={detail.verdict} />

        {/* rationale */}
        {detail.verdict_rationale && (
          <div className="border border-hermes-bone/15 bg-hermes-panel-deep p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-1.5">Engine Rationale</div>
            <p className="text-sm text-hermes-bone/85">{detail.verdict_rationale}</p>
          </div>
        )}

        {/* signal breakdown */}
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-2">
            Signal Breakdown · weights disclosed
          </div>
          <div className="space-y-2">
            {signals.length === 0 && <p className="text-xs font-mono text-hermes-bone/55">No weighted signal breakdown supplied.</p>}
            {signals.map((sig) => (
                <div key={sig.key} className="border border-hermes-bone/15 bg-hermes-panel-deep px-3 py-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-xs text-hermes-bone/85">
                      {SIGNAL_LABELS[sig.key] ?? sig.key}
                      <span className="ml-2 text-[9px] text-hermes-bone/40">weight {(sig.weight * 100).toFixed(0)}%</span>
                    </span>
                    <span className="font-mono text-sm tabular-nums" style={{ color: probColor(sig.value) }}>
                      {(sig.value * 100).toFixed(0)}
                    </span>
                  </div>
                  <div className="h-1 bg-hermes-bone/10">
                    <div className="h-full" style={{ width: `${sig.value * 100}%`, background: probColor(sig.value) }} />
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* checked neighbors */}
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-2">
            Cross-Outlet Neighbors Actually Checked (NLI)
          </div>
          {neighbors.length === 0 ? (
            <p className="font-mono text-xs text-hermes-bone/50 border border-dashed border-hermes-bone/20 p-3">
              No cross-outlet neighbors in corpus yet — this claim is single-source.
              As more articles are ingested and claims extracted, corroboration is re-computed.
            </p>
          ) : (
            <div className="space-y-1.5">
              {neighbors.map((nb, i) => (
                <div key={i} className="flex items-center gap-2 border border-hermes-bone/12 bg-hermes-panel-deep px-3 py-2">
                  <span className={`font-mono text-[10px] font-bold px-1.5 py-0.5 ${
                    nb.stance === 'yes' || nb.stance === 'entailment' ? 'bg-emerald-400/15 text-emerald-300' :
                    nb.stance === 'no' || nb.stance === 'contradiction' ? 'bg-hermes-red-bright/15 text-hermes-red-bright' :
                    'bg-hermes-bone/10 text-hermes-bone/50'
                  }`}>
                    {nb.stance.toUpperCase()}
                  </span>
                  <span className="font-mono text-[10px] text-hermes-bone/40 w-24 truncate">{nb.domain.replace('www.', '')}</span>
                  <span className="text-xs text-hermes-bone/75 truncate flex-1">{nb.claim}</span>
                  <span className="font-mono text-[10px] text-hermes-bone/40 tabular-nums">{(nb.similarity * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <details><summary className="cursor-pointer text-xs font-mono">Full stored evidence metadata</summary><pre className="text-xs whitespace-pre-wrap break-words mt-2">{JSON.stringify(ev, null, 2)}</pre></details>

        {/* entities */}
        {detail.entities && detail.entities.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-2">Grounded Entities</div>
            <div className="flex flex-wrap gap-1.5">
              {detail.entities.map((e, i) => (
                <span key={i} className="chip-brutal !text-[10px] border-hermes-bone/25 text-hermes-bone/70">
                  {e.text} <span className="text-hermes-bone/40">· {e.type}</span>
                </span>
              ))}
            </div>
          </div>
        )}
    </Dialog>
  );
};

export const FactCheck: React.FC = () => {
  const [openId, setOpenId] = useState<string | null>(null);
  const [bandFilter, setBandFilter] = useState('');
  const polling = usePollingPolicy(20000);

  const list = useQuery({
    queryKey: ['verdicts', bandFilter],
    queryFn: ({ signal }) =>
      apiClient.get(`/verdicts${bandFilter ? `?band=${encodeURIComponent(bandFilter)}` : ''}`, { signal }) as Promise<{
        total: number; items: VerdictRow[];
      }>,
    ...polling,
  });

  const stats = useQuery({
    queryKey: ['verdict-stats'],
    queryFn: ({ signal }) => apiClient.get('/verdicts/stats', { signal }) as Promise<{
      total_claims: number;
      distribution: Array<{ band: string; count: number }>;
      outlets: Array<{ name: string; claims: number; supported: number; disputed: number; credibility: number }>;
    }>,
    ...polling,
  });

  const detail = useQuery({
    queryKey: ['verdict-detail', openId],
    queryFn: ({ signal }) => apiClient.get(`/verdicts/${openId}`, { signal }) as Promise<VerdictDetail>,
    enabled: !!openId,
    ...polling,
    refetchInterval: false,
  });

  const leaderboard = useQuery({
    queryKey: ['leaderboard'],
    queryFn: ({ signal }) => apiClient.get('/verdicts/leaderboard', { signal }) as Promise<{
      ranking: Array<{ name: string; credibility: number; claims: number; supported: number; disputed: number }>;
    }>,
    ...polling,
  });

  return (
    <div className="space-y-8">
      {/* Methodology banner — the Guinness-style standard statement */}
      <div className="card-brutal-dark p-5 flex items-start gap-4 border-l-4 border-l-hermes-red">
        <Landmark className="w-6 h-6 shrink-0 mt-0.5" />
        <div className="text-sm leading-relaxed text-hermes-bone/80">
          <span className="font-display text-base text-hermes-bone">GMEE corpus-local assessment.</span>{' '}
          Stored support scores are <strong>uncalibrated, unvalidated heuristics</strong>,
          not probabilities of truth. Corpus corroboration, NLI contradiction,
          outlet counts and other disclosed signals can be incomplete or biased.
          Inspect the returned evidence; neither a band nor a score establishes factual correctness.
        </div>
      </div>

      <ClaimCheck />

      {stats.isLoading && <p role="status" className="text-xs font-mono">Loading stored verdict statistics…</p>}
      {stats.isError && <QueryError title="Verdict statistics unavailable" error={stats.error} onRetry={() => stats.refetch()} retrying={stats.isFetching} />}
      {/* stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card-brutal-dark p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/50">Claims scored</div>
          <div className="text-2xl font-display tabular-nums mt-1">{stats.data?.total_claims ?? '—'}</div>
        </div>
        {(stats.data?.distribution ?? [])
          .filter((d) => d.band !== 'UNSCORED')
          .slice(0, 3)
          .map((d) => {
            const bs = BAND_STYLE[d.band];
            return (
              <div key={d.band} className="card-brutal-dark p-4">
                <div className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/50">
                  {bs?.label ?? d.band}
                </div>
                <div className="text-2xl font-display tabular-nums mt-1">{d.count}</div>
              </div>
            );
          })}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* main verdict feed */}
        <section className="xl:col-span-2 card-brutal-dark p-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-hermes-bone/12 mb-5">
            <h2 className="text-2xl font-display flex items-center gap-2">
              <Scale className="w-5 h-5" /> Verdict Feed
            </h2>
            <select
              aria-label="Stored verdict band filter"
              value={bandFilter}
              onChange={(e) => setBandFilter(e.target.value)}
              className="bg-hermes-panel-deep border border-hermes-bone/25 text-hermes-bone font-mono text-xs px-2 py-1.5 outline-none"
            >
              <option value="">all bands</option>
              <option value="SUPPORTED">SUPPORTED</option>
              <option value="PARTIALLY_SUPPORTED">PARTIALLY SUPPORTED</option>
              <option value="WEAKLY_CORROBORATED">WEAKLY CORROBORATED</option>
              <option value="UNRESOLVED">UNRESOLVED</option>
              <option value="UNSUPPORTED">UNSUPPORTED</option>
              <option value="DISPUTED">DISPUTED</option>
            </select>
          </div>

          {list.isLoading ? (
            <div className="space-y-3">{[...Array(5)].map((_, i) => <div key={i} className="shimmer h-28" />)}</div>
          ) : list.isError ? (
            <QueryError title="Verdict feed unavailable" error={list.error} onRetry={() => list.refetch()} retrying={list.isFetching} />
          ) : (list.data?.items.length ?? 0) === 0 ? (
            <p className="font-mono text-xs text-hermes-bone/55 py-8 text-center">
              No verdicts yet for this filter. No stored claims have been returned.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {list.data?.items.map((r) => (
                <VerdictCard key={r.id} row={r} onOpen={() => setOpenId(r.id)} />
              ))}
            </div>
          )}
        </section>

        {/* outlet credibility leaderboard */}
        <section className="card-brutal-dark p-6 h-fit">
          <h2 className="text-2xl font-display flex items-center gap-2 mb-1">
            <Trophy className="w-5 h-5" /> Outlet Heuristic Scores
          </h2>
          <p className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45 mb-5">
            laplace-smoothed support counts · not validated source credibility
          </p>

          <div className="space-y-2.5">
            {leaderboard.isLoading && <p role="status" className="text-xs font-mono">Loading outlet scores…</p>}
            {leaderboard.isError && <QueryError title="Outlet scores unavailable" error={leaderboard.error} onRetry={() => leaderboard.refetch()} retrying={leaderboard.isFetching} />}
            {leaderboard.isSuccess && leaderboard.data.ranking.length === 0 && <p className="text-xs font-mono text-hermes-bone/55">No outlet scores returned.</p>}
            {leaderboard.data?.ranking.map((o, idx) => (
              <div key={o.name} className="flex items-center gap-3">
                <span className="font-display text-lg w-7 text-hermes-bone/35 tabular-nums">{idx + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-xs text-hermes-bone/80 truncate">{o.name.replace('www.', '')}</span>
                    <span className="font-mono text-xs tabular-nums" style={{ color: probColor(o.credibility) }}>
                      {(o.credibility * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-1 bg-hermes-bone/10">
                    <div className="h-full" style={{ width: `${o.credibility * 100}%`, background: probColor(o.credibility) }} />
                  </div>
                  <div className="font-mono text-[9px] text-hermes-bone/35 mt-0.5 uppercase tracking-wider">
                    {o.claims} claims · {o.supported} supported · {o.disputed} disputed
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      {openId && (detail.data && !detail.isError ? <EvidenceDrawer detail={detail.data} onClose={() => setOpenId(null)} /> : (
        <Dialog labelledBy="verdict-loading-title" onClose={() => setOpenId(null)}>
          <div className="flex items-center justify-between gap-3"><h2 id="verdict-loading-title" className="font-display text-xl">Verdict Dossier</h2><button type="button" aria-label="Close verdict dossier" onClick={() => setOpenId(null)} className="btn-brutal">×</button></div>
          {detail.isError ? <QueryError title="Verdict detail unavailable" error={detail.error} onRetry={() => detail.refetch()} retrying={detail.isFetching} /> : <p role="status" className="font-mono text-xs">Loading stored evidence…</p>}
        </Dialog>
      ))}
    </div>
  );
};
