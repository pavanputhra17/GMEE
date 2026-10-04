import React, { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Flag,
  Dna,
  Gamepad2,
  Volume2,
  VolumeX,
  Trophy,
  Check,
  X,
} from 'lucide-react';
import { extrasApi, MutationChain, ScoopRace } from '../api/extras';
import { apiClient, ApiError } from '../api/client';
import { usePollingPolicy } from '../lib/polling';
import { useAnimationActivity } from '../lib/useAnimationActivity';
import { safeHttpUrl } from '../lib/urls';
import { MutationComparator } from './MutationComparator';
import { QueryError } from './QueryError';
import { sound } from '../lib/sound';

/**
 * Masala Lab — Mutation Comparator · Scoop Races · Mutation DNA · engine-agreement arcade.
 * All real data. Sound is synthesized in-browser (no assets), mutable.
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

const fmtLag = (s: number): string => {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
};

/* ---------------------------------- Scoop Races */

const ScoopRaces: React.FC = () => {
  const polling = usePollingPolicy(60000);
  const q = useQuery({
    queryKey: ['scoops'],
    queryFn: ({ signal }) => extrasApi.scoops(10, { signal }),
    ...polling,
  });

  return (
    <section className="card-brutal-dark p-6">
      <div className="flex items-center gap-2 mb-1">
        <Flag className="w-5 h-5" />
        <h3 className="text-xl font-display">Scoop Races</h3>
        <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/55">earliest in linked corpus</span>
      </div>
      <p className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45 mb-4">
        exact publish-time lag behind the winner · from the corpus
      </p>

      {q.isLoading ? (
        <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="shimmer h-16" />)}</div>
      ) : q.isError ? (
        <QueryError title="Scoop races unavailable" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
      ) : (q.data?.races.length ?? 0) === 0 ? (
        <p className="font-mono text-xs text-hermes-bone/50">No multi-outlet races found yet.</p>
      ) : (
        <div className="space-y-5 max-h-[520px] overflow-y-auto pr-1">
          {q.data?.races.map((race: ScoopRace, ri) => {
            const maxLag = Math.max(1, ...race.racers.map((r) => r.lag_seconds));
            return (
              <div key={ri} className="border border-hermes-bone/12 bg-hermes-panel-deep p-4">
                <div className="text-sm font-medium leading-snug mb-3 text-hermes-bone/90">{race.story}</div>
                <div className="space-y-1.5">
                  {race.racers.map((r) => {
                    const pct = r.lag_seconds === 0 ? 100 : Math.max(6, 100 - (r.lag_seconds / maxLag) * 88);
                    const win = r.position === 0;
                    return (
                      <a key={r.id} href={safeHttpUrl(r.url)} target="_blank" rel="noreferrer"
                         className="group flex items-center gap-2.5">
                        <span className={`font-mono text-[10px] tabular-nums w-14 shrink-0 ${win ? 'text-emerald-400 font-bold' : 'text-hermes-bone/45'}`}>
                          {win ? 'FIRST' : `+${fmtLag(r.lag_seconds)}`}
                        </span>
                        <div className="flex-1 h-4 bg-hermes-bone/8 overflow-hidden relative">
                          <div
                            className="h-full transition-all duration-700 group-hover:brightness-125"
                            style={{ width: `${pct}%`, background: colorFor(r.domain), opacity: win ? 1 : 0.55 }}
                          />
                          <span className="absolute left-2 top-1/2 -translate-y-1/2 font-mono text-[9px] uppercase tracking-wider text-black/75 font-bold">
                            {r.domain?.replace('www.', '')}
                          </span>
                        </div>
                        {win && <Trophy className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                      </a>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

/* ---------------------------------- Mutation DNA */

const MutationDNA: React.FC = () => {
  const [active, setActive] = useState(0);
  const hostRef = useRef<HTMLElement>(null);
  const { animate } = useAnimationActivity(hostRef);
  const polling = usePollingPolicy(120000);
  const q = useQuery({
    queryKey: ['mutations'],
    queryFn: ({ signal }) => extrasApi.mutations(8, { signal }),
    ...polling,
  });

  const chain: MutationChain | undefined = q.data?.chains[active];
  const [inspect, setInspect] = useState<string | null>(null);

  // auto-cycle highlight through versions (the "helix read")
  const [cursor, setCursor] = useState(0);
  useEffect(() => {
    setCursor(0);
    if (!chain || !animate || chain.versions.length < 2) return;
    const iv = setInterval(() => {
      setCursor((c) => (c + 1) % chain.versions.length);
    }, 1600);
    return () => clearInterval(iv);
  }, [chain, animate]);

  return (
    <section ref={hostRef} className="card-brutal-dark p-6">
      <div className="flex items-center gap-2 mb-1">
        <Dna className="w-5 h-5" />
        <h3 className="text-xl font-display">Mutation DNA</h3>
        <span className="chip-brutal border-hermes-bone/25 text-hermes-bone/55">same claim, drifting wording</span>
      </div>
      <p className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45 mb-4">
        similarity-linked corpus groups · wording drift does not prove transmission
      </p>

      {/* chain selector */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {(q.data?.chains ?? []).map((c, i) => (
          <button key={c.chain_id} onClick={() => setActive(i)}
            className={`px-2.5 py-1 border font-mono text-[10px] uppercase tracking-wider ${
              i === active ? 'border-hermes-red bg-hermes-red/15 text-white' : 'border-hermes-bone/20 text-hermes-bone/55 hover:border-hermes-bone/40'
            }`}>
            #{i + 1} · {c.distinct_outlets} outlets
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <div className="shimmer h-48" />
      ) : q.isError ? (
        <QueryError title="Mutation groups unavailable" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
      ) : !chain ? (
        <p className="font-mono text-xs text-hermes-bone/50">No cross-outlet mutation chains yet — more corpus needed.</p>
      ) : (
        <div className="relative pl-6">
          {/* helix spine */}
          <div className="absolute left-2 top-2 bottom-2 w-0.5 bg-gradient-to-b from-hermes-red via-hermes-red-bright to-transparent" />
          {chain.versions.map((v, i) => (
            <button type="button" key={v.id} onClick={() => setInspect(v.id)}
               className={`relative block w-full text-left mb-2 border px-4 py-3 transition-all duration-500 ${
                 i === cursor
                   ? 'border-hermes-red-bright bg-hermes-red/10 translate-x-2'
                   : i < cursor ? 'border-hermes-bone/10 opacity-40' : 'border-hermes-bone/15'
               }`}>
              <span className="absolute -left-[21px] top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-ink"
                    style={{ background: colorFor(v.domain) }} />
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[9px] uppercase tracking-wider text-hermes-bone/45">
                  v{i + 1} · {v.domain?.replace('www.', '')}
                </span>
                <span className="font-mono text-[9px] text-hermes-bone/30">
                  {v.published_at ? new Date(v.published_at).toLocaleDateString() : ''}
                </span>
              </div>
              <div className={`text-xs mt-1 leading-relaxed ${i === cursor ? 'text-white' : 'text-hermes-bone/70'}`}>
                “{v.text}”
              </div>
            </button>
          ))}
        </div>
      )}
      {inspect && <LineagePanel claimId={inspect} />}
    </section>
  );
};

/* ---------------------------------- Mutation Inspector (lineage + typed diff) */

const LineagePanel: React.FC<{ claimId: string }> = ({ claimId }) => {
  const polling = usePollingPolicy();
  const q = useQuery({
    queryKey: ['lineage', claimId],
    queryFn: ({ signal }) => extrasApi.lineage(claimId, { signal }),
    ...polling,
    refetchInterval: false,
  });
  const [di, setDi] = useState(0);

  if (q.isLoading) return <div className="shimmer h-40 mt-5" />;
  if (q.isError) return <QueryError title="Mutation lineage unavailable" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />;
  if (!q.data) {
    return (
      <p className="font-mono text-xs text-hermes-bone/50 mt-5 border border-dashed border-hermes-bone/20 p-3">
        No EVOLVED_FROM lineage for this claim — it has no recorded mutation links yet.
      </p>
    );
  }

  const data = q.data;
  const diff = data.diffs[di];
  const pair = diff
    ? `v${diff.from_index + 1} → v${diff.to_index + 1}`
    : 'no version pairs';

  return (
    <div className="border-t border-hermes-bone/15 mt-5 pt-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45">
          Mutation Inspector · {data.counts.component_claims} versions · {data.counts.edges} links
        </span>
        {data.diffs.length > 0 && (
          <button
            onClick={() => setDi((d) => (d + 1) % data.diffs.length)}
            className="btn-ghost-brutal !py-1 !px-2 !text-[10px] !text-hermes-bone !border-hermes-bone/25"
          >
            {pair} ↻
          </button>
        )}
      </div>

      {!diff ? <p className="text-xs font-mono text-hermes-bone/55">No recorded version diff returned.</p> : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-1.5 items-center">
            {diff.mutation_types.map((t) => (
              <span
                key={t}
                className="chip-brutal !text-[10px] border-hermes-red/60 text-hermes-red-bright"
              >
                {t}
              </span>
            ))}
            <span className="chip-brutal !text-[10px] border-hermes-bone/25 text-hermes-bone/60">
              sim {(diff.similarity * 100).toFixed(0)}%
            </span>
          </div>

          {(diff.numeric_changes.length > 0 || diff.entity_changes.length > 0) && (
            <div className="font-mono text-[11px] leading-relaxed">
              {diff.numeric_changes.length > 0 && (
                <span className="text-hermes-bone/40 uppercase tracking-widest text-[9px] mr-2">
                  numbers
                </span>
              )}
              {diff.numeric_changes.map((c, i) => (
                <span key={`n${i}`} className="mr-3">
                  {c.removed && <span className="text-hermes-red-bright line-through">{c.removed}</span>}
                  {c.removed && c.added && <span className="text-hermes-bone/40"> → </span>}
                  {c.added && <span className="text-emerald-400">{c.added}</span>}
                </span>
              ))}
              {diff.entity_changes.length > 0 && (
                <span className="text-hermes-bone/40 uppercase tracking-widest text-[9px] mr-2 ml-1">
                  entities
                </span>
              )}
              {diff.entity_changes.map((c, i) => (
                <span key={`e${i}`} className="mr-3">
                  {c.removed && <span className="text-hermes-red-bright line-through">{c.removed}</span>}
                  {c.removed && c.added && <span className="text-hermes-bone/40"> → </span>}
                  {c.added && <span className="text-emerald-400">{c.added}</span>}
                </span>
              ))}
            </div>
          )}

          {diff.hedge_changes.length > 0 && (
            <div className="font-mono text-[11px] leading-relaxed">
              <span className="text-hermes-bone/40 uppercase tracking-widest text-[9px] mr-2">
                hedging
              </span>
              {diff.hedge_changes.map((h, i) => (
                <span
                  key={i}
                  className={`mr-3 ${h.direction === 'lost' ? 'text-hermes-red-bright' : 'text-emerald-400'}`}
                >
                  {h.direction === 'lost' ? '−' : '+'}
                  {h.word}
                </span>
              ))}
            </div>
          )}

          <div className="text-xs leading-relaxed border border-hermes-bone/10 bg-hermes-panel-deep p-3">
            {diff.segments.map((s, i) =>
              s.type === 'same' ? (
                <span key={i} className="text-hermes-bone/40">
                  {s.old}{' '}
                </span>
              ) : (
                <span key={i}>
                  <span className="text-hermes-red-bright line-through">{s.old}</span>{' '}
                  <span className="text-emerald-400">{s.new}</span>{' '}
                </span>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
};

/* ---------------------------------- Engine-agreement Arcade */

const Arcade: React.FC = () => {
  const [claim, setClaim] = useState<{ id: string; text: string; domain: string | null } | null>(null);
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState<'SUPPORTED' | 'DISPUTED' | null>(null);
  const [revealed, setRevealed] = useState<{ band: string; prob: number | null } | null>(null);
  const [revealing, setRevealing] = useState(false);
  const [arcadeError, setArcadeError] = useState<unknown>(null);
  const [score, setScore] = useState({ right: 0, wrong: 0, streak: 0 });
  const [soundOn, setSoundOn] = useState(false);

  const nextClaim = async () => {
    setLoading(true);
    setRevealed(null);
    setVerdict(null);
    setArcadeError(null);
    setClaim(null);
    try {
      const c = await apiClient.get('/verdicts/game/claim') as { id: string; text: string; domain: string | null };
      if (!c?.id || typeof c.text !== 'string') throw new ApiError(200, c, 'The arcade API returned no claim.');
      setClaim(c);
    } catch (error) {
      setArcadeError(error);
      setClaim(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void nextClaim(); }, []);

  const guess = async (g: 'SUPPORTED' | 'DISPUTED') => {
    if (!claim || revealed || revealing) return;
    setVerdict(g);
    setRevealing(true);
    setArcadeError(null);
    try {
      const d = await apiClient.get(`/verdicts/${claim.id}`) as { verdict: string; probability: number | null };
      setRevealed({ band: d.verdict, prob: d.probability });
      const agreed = g === d.verdict;
      if (agreed) {
        if (soundOn) sound.win();
        setScore((s) => ({ right: s.right + 1, wrong: s.wrong, streak: s.streak + 1 }));
      } else {
        if (soundOn) sound.lose();
        setScore((s) => ({ right: s.right, wrong: s.wrong + 1, streak: 0 }));
      }
    } catch (error) {
      setArcadeError(error);
      setRevealed(null);
    } finally {
      setRevealing(false);
    }
  };

  return (
    <section className="card-brutal-dark p-6">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Gamepad2 className="w-5 h-5" />
          <h3 className="text-xl font-display">Agree with engine</h3>
          <span className="chip-brutal border-hermes-red text-hermes-red-bright">ARCADE</span>
        </div>
        <button
          onClick={() => { const m = !soundOn; setSoundOn(m); sound.setMuted(!m); }}
          className="btn-ghost-brutal !py-1 !px-2 !text-hermes-bone !border-hermes-bone/25"
          title={soundOn ? 'sound on' : 'sound off'}
                    aria-label={soundOn ? 'Mute arcade sound' : 'Enable arcade sound'}
                    aria-pressed={soundOn}
        >
          {soundOn ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
        </button>
      </div>
      <p className="text-[10px] font-mono uppercase tracking-widest text-hermes-bone/45 mb-4">
        compare your band choice with the engine · agreement is not correctness
      </p>

      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="border border-hermes-bone/12 bg-hermes-panel-deep p-2 text-center">
          <div className="text-[9px] font-mono uppercase tracking-widest text-hermes-bone/45">Matched engine</div>
          <div className="font-display text-lg text-emerald-400 tabular-nums">{score.right}</div>
        </div>
        <div className="border border-hermes-bone/12 bg-hermes-panel-deep p-2 text-center">
          <div className="text-[9px] font-mono uppercase tracking-widest text-hermes-bone/45">Different from engine</div>
          <div className="font-display text-lg text-hermes-red-bright tabular-nums">{score.wrong}</div>
        </div>
        <div className="border border-hermes-bone/12 bg-hermes-panel-deep p-2 text-center">
          <div className="text-[9px] font-mono uppercase tracking-widest text-hermes-bone/45">Agreement streak</div>
          <div className="font-display text-lg text-white tabular-nums">{score.streak}×</div>
        </div>
      </div>

      <p className="text-xs text-hermes-bone/55 mb-4">Local round counts only. Engine bands and support scores are unvalidated heuristics, not a truth benchmark.</p>
      {arcadeError != null && <QueryError title={claim ? 'Engine reveal unavailable' : 'Arcade claim unavailable'} error={arcadeError} onRetry={() => claim && verdict ? guess(verdict) : nextClaim()} retrying={loading || revealing} />}
      {loading ? (
        <div role="status" aria-label="Loading arcade claim" className="shimmer h-28" />
      ) : !claim ? (
        !arcadeError && <p className="text-xs font-mono text-hermes-bone/55">No arcade claims returned.</p>
      ) : (
        <div className="border border-hermes-bone/20 bg-hermes-panel-deep p-4">
          <div className="font-mono text-[9px] uppercase tracking-widest text-hermes-bone/40 mb-2">
            from {claim.domain?.replace('www.', '')} · your call:
          </div>
          <p className="text-sm leading-relaxed text-hermes-bone/90 mb-4">“{claim.text}”</p>

          {!revealed ? (
            <div className="grid grid-cols-2 gap-2">
              <button disabled={revealing} onClick={() => void guess('SUPPORTED')}
                className="btn-brutal !bg-emerald-500/15 !text-emerald-300 !border-emerald-400/50 hover:!bg-emerald-500/30 py-3">
                <Check className="w-4 h-4 inline mr-1" /> SUPPORTED
              </button>
              <button disabled={revealing} onClick={() => void guess('DISPUTED')}
                className="btn-brutal !bg-hermes-red/15 !text-hermes-red-bright !border-hermes-red-bright/50 hover:!bg-hermes-red/35 py-3">
                <X className="w-4 h-4 inline mr-1" /> DISPUTED
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {(() => {
                const agreed = verdict === revealed.band;
                return (
                  <>
                    <div className={`border p-3 font-mono text-xs ${agreed ? 'border-emerald-400/50 text-emerald-300 bg-emerald-400/5' : 'border-hermes-red-bright/50 text-hermes-red-bright bg-hermes-red/5'}`}>
                      {agreed ? 'MATCHED ENGINE. ' : 'DIFFERENT FROM ENGINE. '}Engine band: {revealed.band.replace(/_/g, ' ')}
                      {' '}· heuristic support: {revealed.prob == null ? 'not supplied' : `${(revealed.prob * 100).toFixed(1)}%`} (unvalidated)
                    </div>
                    <button onClick={nextClaim} className="btn-brutal w-full py-3">
                      NEXT CLAIM →
                    </button>
                  </>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

/* ---------------------------------- page */

const MasalaLab: React.FC = () => (
  <div className="space-y-8">
    <MutationComparator />
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <ScoopRaces />
      <MutationDNA />
    </div>
    <Arcade />
  </div>
);

export default MasalaLab;
