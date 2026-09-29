import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Database,
  Network,
  Terminal,
  HardDrive,
  Radar,
  GitBranch,
  ShieldCheck,
} from 'lucide-react';
import { fetchDashboard } from '../api/dashboard';
import { AsciiGlobe } from '../components/AsciiGlobe';
import { AsciiTicker } from '../components/AsciiTicker';
import { AsciiReveal } from '../components/AsciiReveal';
import { LiveAuditFeed } from '../components/LiveAuditFeed';

/**
 * GMEE landing page — editorial-brutalist poster in the red-immersion palette.
 * One solid-crimson moment (footer CTA band); the hero is an ink panel where
 * the animated ASCII globe carries all the drama. Sections reveal on scroll
 * (once, gentle, reduced-motion safe).
 */

/* -------------------------------- data -------------------------------- */

const DEFAULT_HERO_STATS = [
  { k: '10,000+', label: 'claims indexed' },
  { k: '27,132', label: 'graph nodes' },
  { k: '80,107', label: 'propagation edges' },
  { k: '3 / 3', label: 'live services' },
];

const TICKER_ITEMS = [
  'CLAIM MUTATIONS TRACED IN REAL TIME',
  'PGVECTOR · HNSW · 768-D EMBEDDINGS',
  'NEO4J PROPAGATION TOPOLOGY',
  'APPEND-ONLY AUDIT STREAM',
  'REDIS-METERED INGEST QUEUE',
];

const CAPABILITIES = [
  {
    icon: Database,
    title: 'Semantic Vector Search',
    body: 'Every claim embedded with all-mpnet-base-v2 into pgvector. Nearest-neighbor cosine search surfaces mutating variants of a narrative across millions of documents.',
    meta: 'PGVECTOR · HNSW · 768-D',
  },
  {
    icon: Network,
    title: 'Propagation Graph Engine',
    body: 'Claims, actors, sources, and botnets mapped as a living Neo4j topology. Watch a narrative jump clusters and identify coordinated amplification.',
    meta: 'NEO4J · BOLT · CYPHER',
  },
  {
    icon: Terminal,
    title: 'Live Audit Stream',
    body: 'Every index write, sync batch, and pipeline verification streams into a tamper-evident telemetry feed. The engine shows its work.',
    meta: 'REAL-TIME · APPEND-ONLY',
  },
  {
    icon: HardDrive,
    title: 'Rate-Limited Ingest Queue',
    body: 'A Redis-backed queue meters ingestion and blocks revoked tokens, so the corpus grows on our terms — not the spammer\u2019s.',
    meta: 'REDIS · JWT BLOCKLIST',
  },
];

const STEPS = [
  {
    n: '01',
    title: 'Ingest',
    body: 'Articles, posts, and broadcasts flow through the LLM pipeline, which extracts factual claims and normalizes them into embeddings.',
  },
  {
    n: '02',
    title: 'Evolve',
    body: 'Each new claim is matched against the vector index and grafted into the propagation graph — mutations, lineage, and all.',
  },
  {
    n: '03',
    title: 'Trace',
    body: 'Open the command center to watch narratives spread in real time: risk scores, cluster maps, and the full audit trail.',
  },
];

export const Landing: React.FC = () => {
  const { data: snapshot } = useQuery({
    queryKey: ['landing-dashboard-summary'],
    queryFn: fetchDashboard,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const heroStats = useMemo(() => {
    if (!snapshot) return DEFAULT_HERO_STATS;

    const claimsCount = snapshot.claims_total ?? snapshot.embedded_claims;
    const claimsFormatted =
      typeof claimsCount === 'number' && claimsCount > 0
        ? claimsCount.toLocaleString()
        : DEFAULT_HERO_STATS[0].k;

    const graphNodesCount = snapshot.graph?.nodes
      ? Object.values(snapshot.graph.nodes).reduce((acc, curr) => acc + curr, 0)
      : null;
    const graphNodesFormatted =
      typeof graphNodesCount === 'number' && graphNodesCount > 0
        ? graphNodesCount.toLocaleString()
        : DEFAULT_HERO_STATS[1].k;

    const edgesCount = snapshot.graph?.relationships;
    const edgesFormatted =
      typeof edgesCount === 'number' && edgesCount > 0
        ? edgesCount.toLocaleString()
        : DEFAULT_HERO_STATS[2].k;

    const services = snapshot.services;
    const liveCount = services
      ? [services.postgres, services.neo4j, services.redis].filter(
          (s) => s === 'ok'
        ).length
      : 3;
    const servicesFormatted = `${liveCount} / 3`;

    return [
      { k: claimsFormatted, label: 'claims indexed' },
      { k: graphNodesFormatted, label: 'graph nodes' },
      { k: edgesFormatted, label: 'propagation edges' },
      { k: servicesFormatted, label: 'live services' },
    ];
  }, [snapshot]);

  return (
    <div className="min-h-screen flex flex-col relative">
      {/* Paper grain */}
      <div className="fixed inset-0 z-0 pointer-events-none grain-overlay" />

      {/* ------------------------------ Top bar ------------------------------ */}
      <header className="relative z-10 border-b border-hermes-ink/90 bg-hermes-paper">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="chip-brutal bg-hermes-red text-hermes-bone border-hermes-ink/90">
              GMEE
            </span>
            <span className="hidden sm:inline text-[11px] font-mono uppercase tracking-widest text-hermes-ink/60">
              v1.0 telemetry
            </span>
          </div>
          <a href="#/dashboard" className="btn-brutal !py-1.5 !px-3">
            Command Center <ArrowRight className="w-3.5 h-3.5" />
          </a>
        </div>
      </header>

      {/* -------------------------------- Hero -------------------------------- */}
      <section className="relative z-10 bg-hermes-ink text-hermes-bone border-b border-hermes-ink/90">
        <div className="max-w-7xl mx-auto px-4 md:px-8 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center py-14 md:py-20">
          {/* Copy */}
          <div className="flex flex-col items-start gap-6">
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-hermes-red-bright flex items-center gap-2">
              <Radar className="w-4 h-4" />
              Global Misinformation Evolution Engine
            </p>
            <h1 className="text-5xl md:text-7xl font-display leading-[0.98] tracking-tight">
              Watch narratives
              <br />
              mutate{' '}
              <em className="text-hermes-red-bright">live</em>.
            </h1>
            <p className="text-sm md:text-base font-mono leading-relaxed text-hermes-bone/70 max-w-md">
              GMEE ingests the world&apos;s news stream, extracts claims, embeds
              them, and grafts them into a propagation graph — so you can trace
              how a falsehood forms, spreads, and evolves across the network.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <a href="#/dashboard" className="btn-brutal">
                Launch Telemetry <ArrowRight className="w-4 h-4" />
              </a>
              <a
                href="#about"
                className="btn-ghost-brutal !text-hermes-bone !border-hermes-bone/40 hover:!border-hermes-bone"
              >
                What is GMEE?
              </a>
            </div>
          </div>

          {/* Globe */}
          <div className="relative w-full max-w-[520px] aspect-square mx-auto">
            <AsciiGlobe className="absolute inset-0" />
            <span className="absolute top-2 right-2 font-mono text-[10px] tracking-widest text-hermes-red-bright/80 uppercase">
              ◉ live projection · ascii raster
            </span>
            <span className="absolute bottom-2 left-2 font-mono text-[10px] tracking-widest text-hermes-bone/40 uppercase">
              rev 48s · scan 14s
            </span>
          </div>
        </div>

        {/* Stats strip */}
        <div className="border-t border-hermes-bone/15">
          <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            {heroStats.map((s) => (
              <div key={s.label} className="flex flex-col">
                <span className="font-display text-2xl md:text-3xl tabular-nums">
                  {s.k}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/50">
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------- Ticker stripe --------------------------- */}
      <div
        className="relative z-10 border-b border-hermes-ink/90 bg-hermes-paper py-2.5 font-mono text-[11px] font-bold uppercase tracking-[0.18em] text-hermes-ink/80"
      >
        <AsciiTicker items={TICKER_ITEMS} speed={10} />
      </div>

      {/* ------------------------------- About -------------------------------- */}
      <main id="about" className="relative z-10 flex-1">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-14 md:py-20 flex flex-col gap-12">
          <AsciiReveal className="flex flex-col gap-2 max-w-2xl">
            <p className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-hermes-red">
              What this site is
            </p>
            <h2 className="text-3xl md:text-5xl font-display tracking-tight">
              An observatory for engineered truth decay.
            </h2>
            <p className="text-sm font-mono leading-relaxed text-hermes-ink/70">
              Misinformation doesn&apos;t appear fully formed — it evolves. GMEE
              treats every claim as an organism: embedded, indexed, and tracked
              through its mutations. Four subsystems make that possible.
            </p>
          </AsciiReveal>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {CAPABILITIES.map((c) => (
              <AsciiReveal key={c.title}>
                <div className="card-brutal card-brutal-hover p-6 flex flex-col gap-3 h-full">
                  <div className="flex items-center justify-between">
                    <span className="p-2.5 border border-hermes-ink/90 bg-hermes-red text-hermes-bone">
                      <c.icon className="w-5 h-5" />
                    </span>
                    <span className="font-mono text-[9px] uppercase tracking-widest text-hermes-ink/40">
                      {c.meta}
                    </span>
                  </div>
                  <h3 className="text-xl font-display">{c.title}</h3>
                  <p className="text-xs font-mono leading-relaxed text-hermes-ink/70">
                    {c.body}
                  </p>
                </div>
              </AsciiReveal>
            ))}
          </div>

          {/* Pipeline steps */}
          <AsciiReveal>
            <div className="border border-hermes-ink/90 bg-hermes-blush shadow-[4px_4px_0_0_rgba(26,6,8,1)]">
              <div className="px-5 md:px-6 py-3 border-b border-hermes-ink/90 bg-hermes-red text-hermes-bone flex items-center gap-2">
                <GitBranch className="w-4 h-4" />
                <span className="font-mono text-[11px] font-bold uppercase tracking-widest">
                  The pipeline
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-hermes-ink/20">
                {STEPS.map((s) => (
                  <div key={s.n} className="p-5 md:p-6 flex flex-col gap-2">
                    <span className="font-mono text-[11px] font-bold text-hermes-red">
                      {s.n}
                    </span>
                    <h3 className="text-lg font-display">{s.title}</h3>
                    <p className="text-xs font-mono leading-relaxed text-hermes-ink/70">
                      {s.body}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </AsciiReveal>

          {/* ------------------------ Live engine output ------------------------ */}
          <AsciiReveal>
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.25fr] gap-8 items-center">
              <div className="flex flex-col gap-3">
                <p className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-hermes-red">
                  Live engine output
                </p>
                <h2 className="text-3xl md:text-4xl font-display tracking-tight">
                  The engine shows its work.
                </h2>
                <p className="text-sm font-mono leading-relaxed text-hermes-ink/70">
                  Nothing hides inside GMEE. Index writes, graph syncs, and
                  pipeline verifications land in an append-only stream — the
                  same feed operators watch in the command center.
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <span className="chip-brutal bg-hermes-ink text-hermes-bone border-hermes-ink/90">
                    Append-only
                  </span>
                  <span className="chip-brutal border-hermes-ink/60 text-hermes-ink/70">
                    9s cadence
                  </span>
                  <span className="chip-brutal border-hermes-ink/60 text-hermes-ink/70">
                    Tamper-evident
                  </span>
                </div>
              </div>
              <LiveAuditFeed />
            </div>
          </AsciiReveal>
        </div>
      </main>

      {/* ------------------------------ CTA band ------------------------------ */}
      <footer className="relative z-10 bg-hermes-red text-hermes-bone border-t border-hermes-ink/90">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex flex-col gap-1">
            <h2 className="text-3xl md:text-4xl font-display tracking-tight">
              Ready to trace the spread?
            </h2>
            <p className="font-mono text-xs text-hermes-bone/75 flex items-center gap-2">
              <ShieldCheck className="w-3.5 h-3.5" />
              Live telemetry · simulated fallback when the backend sleeps
            </p>
          </div>
          <a
            href="#/dashboard"
            className="inline-flex items-center gap-2 border border-hermes-ink/90 bg-hermes-ink text-hermes-bone font-mono text-xs font-bold uppercase tracking-wider px-5 py-3 shadow-[3px_3px_0_0_rgba(26,6,8,1)] transition-all duration-150 hover:-translate-x-0.5 hover:-translate-y-0.5 hover:shadow-[5px_5px_0_0_rgba(26,6,8,1)] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none cursor-pointer"
          >
            Open Command Center <ArrowRight className="w-4 h-4" />
          </a>
        </div>
        <div className="border-t border-hermes-bone/20">
          <div className="max-w-7xl mx-auto px-4 md:px-8 py-3 font-mono text-[10px] uppercase tracking-widest text-hermes-bone/60 flex items-center justify-between">
            <span>GMEE // Global Misinformation Evolution Engine</span>
            <span className="hidden sm:inline">pgvector · neo4j · redis</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
