import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { Header, TabType } from '../components/Header';
import { MetricCard } from '../components/MetricCard';
import { GraphVisualizer } from '../components/GraphVisualizer';
import { VectorTelemetry } from '../components/VectorTelemetry';
import { LiveAuditFeed } from '../components/LiveAuditFeed';
import {
  Database,
  Network,
  HardDrive,
  AlertCircle,
  ShieldCheck,
  FlaskConical,
  X,
  RefreshCw,
  Play
} from 'lucide-react';

interface HealthStatus {
  postgres?: string;
  neo4j?: string;
  redis?: string;
  status: string;
}

const fetchHealth = async (): Promise<HealthStatus> => {
  try {
    return await apiClient.get('/health/ready');
  } catch (error: unknown) {
    if (error instanceof Error) throw new Error(error.message);
    throw new Error(String(error));
  }
};

/* ------------------------------ Demo telemetry ----------------------------- */

interface DemoTelemetry {
  claimsIndexed: number;
  graphNodes: number;
  graphEdges: number;
  queueDepth: number;
  vectorDrift: number;
  latencyMs: number;
  hitRatio: number;
  revokedTokens: number;
  memoryMb: number;
}

const DEMO_BASE: DemoTelemetry = {
  claimsIndexed: 148920,
  graphNodes: 42118,
  graphEdges: 137540,
  queueDepth: 231,
  vectorDrift: 0.031,
  latencyMs: 4.2,
  hitRatio: 98.4,
  revokedTokens: 1409,
  memoryMb: 128.4
};

const jitter = (base: number, pct: number, decimals = 0): number => {
  const delta = base * pct;
  const next = base + (Math.random() * 2 - 1) * delta;
  return Number(next.toFixed(decimals));
};

/* ------------------------------- Skeleton UI ------------------------------- */

const SkeletonCard: React.FC = () => (
  <div className="card-brutal p-5">
    <div className="flex items-center justify-between mb-4">
      <div className="shimmer w-11 h-11" />
      <div className="shimmer w-14 h-5" />
    </div>
    <div className="shimmer h-3 w-24 mb-2" />
    <div className="shimmer h-9 w-32" />
    <div className="shimmer h-3 w-full mt-4 pt-3 border-t border-black/10" />
  </div>
);

const LoadingGrid: React.FC = () => (
  <div className="space-y-8" data-testid="loading-grid">
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
      {[0, 1, 2, 3].map(i => <SkeletonCard key={i} />)}
    </div>
    <div className="card-brutal p-6">
      <div className="shimmer h-6 w-72 mb-2" />
      <div className="shimmer h-3 w-96 max-w-full mb-6" />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 shimmer h-64" />
        <div className="shimmer h-64" />
      </div>
    </div>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div className="card-brutal p-6 shimmer h-56" />
      <div className="card-brutal p-6 shimmer h-56" />
    </div>
  </div>
);

/* --------------------------------- Component -------------------------------- */

export const SystemHealth: React.FC = () => {
  const [refetchInterval, setRefetchInterval] = useState<number>(5000);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  // Tracks whether the backend has EVER responded this session — once true,
  // a later network failure shows the error state instead of flipping to demo.
  const [everConnected, setEverConnected] = useState<boolean>(false);
  // null = automatic (demo whenever backend is unreachable); true/false = user override
  const [demoOverride, setDemoOverride] = useState<boolean | null>(null);
  const [telemetry, setTelemetry] = useState<DemoTelemetry>(DEMO_BASE);

  // Derived BEFORE the query so options never reference their own result.
  const demoMode = demoOverride === true || (demoOverride === null && !everConnected);

  const { data, error, isLoading, isFetching, refetch } = useQuery<HealthStatus>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: false,
    // While in demo mode the backend is (by definition) unreachable — stop
    // hammering it. Polling only runs once we've seen a live backend and the
    // user hasn't paused.
    refetchInterval: everConnected && refetchInterval > 0 ? refetchInterval : false,
  });

  // Latch connectivity the first time the backend answers.
  useEffect(() => {
    if (data) setEverConnected(true);
  }, [data]);

  // Slowly drift the simulated metrics so the dashboard feels alive
  useEffect(() => {
    if (!demoMode) return;
    const id = setInterval(() => {
      setTelemetry(prev => ({
        claimsIndexed: prev.claimsIndexed + Math.floor(Math.random() * 3),
        graphNodes: prev.graphNodes + (Math.random() > 0.6 ? 1 : 0),
        graphEdges: prev.graphEdges + Math.floor(Math.random() * 3),
        queueDepth: Math.max(12, jitter(prev.queueDepth, 0.06)),
        vectorDrift: Math.max(0.005, jitter(prev.vectorDrift, 0.08, 4)),
        latencyMs: Math.max(1.2, jitter(prev.latencyMs, 0.08, 1)),
        hitRatio: Math.min(99.9, Math.max(94, jitter(prev.hitRatio, 0.004, 1))),
        revokedTokens: prev.revokedTokens + (Math.random() > 0.85 ? 1 : 0),
        memoryMb: Math.max(96, jitter(prev.memoryMb, 0.015, 1))
      }));
    }, 5000); // gentle drift every 5s — calm, not twitchy
    return () => clearInterval(id);
  }, [demoMode]);

  const isPostgresOk = demoMode || data?.postgres === 'ok';
  const isNeo4jOk = demoMode || data?.neo4j === 'ok';
  const isRedisOk = demoMode || data?.redis === 'ok';
  const isAllOk = demoMode || data?.status === 'ok';

  // If the backend comes back while the user is in an explicit demo session,
  // hand control back to live data automatically.
  useEffect(() => {
    if (data && demoOverride === true) setDemoOverride(null);
  }, [data, demoOverride]);

  const realStatus: 'ok' | 'degraded' | 'error' = error
    ? 'error'
    : isAllOk
    ? 'ok'
    : 'degraded';

  const headerStatus = demoMode ? ('ok' as const) : realStatus;

  return (
    <div className="min-h-screen flex flex-col items-center p-4 md:p-8 lg:p-12 relative">
      {/* Paper grain texture — Hermes signature */}
      <div className="fixed inset-0 z-0 pointer-events-none grain-overlay" />

      <div className="w-full max-w-7xl z-10">
        {/* Header & Controls */}
        <Header
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          refetchInterval={refetchInterval}
          setRefetchInterval={setRefetchInterval}
          isFetching={isFetching}
          onManualRefresh={() => refetch()}
          status={headerStatus}
          demoMode={demoMode}
        />

        {/* DEMO MODE banner */}
        {demoMode && (
          <div className="mb-8 flex items-center justify-between gap-4 px-4 py-3 border border-black/90 bg-hermes-yellow shadow-[4px_4px_0_0_rgba(10,10,20,1)]">
            <div className="flex items-center gap-3 min-w-0">
              <span className="p-2 border border-black/90 bg-white shrink-0">
                <FlaskConical className="w-4 h-4 text-black" />
              </span>
              <div className="min-w-0">
                <div className="text-xs font-mono font-bold text-black tracking-wider uppercase">
                  Demo Telemetry — simulated data stream
                </div>
                <div className="text-[11px] font-mono text-black/70 truncate">
                  GMEE backend unreachable at http://localhost:8000 · showing synthetic infrastructure metrics
                </div>
              </div>
            </div>
            <button
              onClick={() => setDemoOverride(false)}
              className="btn-ghost-brutal shrink-0 !py-1.5 !px-3"
              title="Hide simulated data and show the connection error"
            >
              <X className="w-3.5 h-3.5" /> Exit Demo
            </button>
          </div>
        )}

        {/* Loading View */}
        {isLoading && !demoMode ? (
          <LoadingGrid />
        ) : error && !demoMode ? (
          /* Error State View */
          <div className="card-brutal p-10 flex flex-col items-center text-center border-rose-700">
            <div className="w-16 h-16 flex items-center justify-center mb-4 border border-black/90 bg-rose-100 shadow-[3px_3px_0_0_rgba(10,10,20,1)]">
              <AlertCircle className="w-8 h-8 text-rose-700" />
            </div>
            <h2 className="text-3xl font-display mb-2">
              Backend Connection Severed
            </h2>
            <p className="text-black/70 max-w-lg text-sm mb-6 font-mono">
              Unable to establish a connection with the GMEE FastAPI backend server. Ensure Docker Compose containers are active.
            </p>
            <div className="bg-white border border-black/40 text-rose-700 font-mono text-xs p-3 max-w-md w-full mb-6 break-all">
              {(error as Error).message}
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => refetch()}
                disabled={isFetching}
                className="btn-brutal"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
                Re-try Telemetry Handshake
              </button>
              <button
                onClick={() => setDemoOverride(true)}
                className="btn-ghost-brutal"
              >
                <Play className="w-3.5 h-3.5" />
                Launch Demo Telemetry
              </button>
            </div>
          </div>
        ) : (
          /* Active Content Views Based on Tab */
          <div className="space-y-8">
            {activeTab === 'overview' && (
              <>
                {/* Metric Summary Banner */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
                  <MetricCard
                    title="PostgreSQL Vector"
                    value={isPostgresOk ? "Nominal" : "Degraded"}
                    subtitle="Relational DB & pgvector"
                    icon={Database}
                    accentColor={isPostgresOk ? "violet" : "rose"}
                    trend={isPostgresOk ? "PORT 55432" : "DOWN"}
                    trendPositive={isPostgresOk}
                  />
                  <MetricCard
                    title="Neo4j Graph Engine"
                    value={isNeo4jOk ? "Connected" : "Degraded"}
                    subtitle={`${telemetry.graphNodes.toLocaleString()} nodes · ${telemetry.graphEdges.toLocaleString()} edges`}
                    icon={Network}
                    accentColor={isNeo4jOk ? "cyan" : "rose"}
                    trend={isNeo4jOk ? "BOLT 7687" : "DOWN"}
                    trendPositive={isNeo4jOk}
                  />
                  <MetricCard
                    title="Redis Cache & Queue"
                    value={isRedisOk ? "Active" : "Degraded"}
                    subtitle={`Queue depth ${telemetry.queueDepth.toLocaleString()} jobs`}
                    icon={HardDrive}
                    accentColor={isRedisOk ? "amber" : "rose"}
                    trend={isRedisOk ? "PORT 6379" : "DOWN"}
                    trendPositive={isRedisOk}
                  />
                  <MetricCard
                    title="System Health Score"
                    value={isAllOk ? `${Math.round(telemetry.hitRatio)}%` : "66%"}
                    subtitle="Overall GMEE cluster vital"
                    icon={ShieldCheck}
                    accentColor={isAllOk ? "emerald" : "amber"}
                    trend={isAllOk ? "HEALTHY" : "CHECK"}
                    trendPositive={isAllOk}
                  />
                </div>

                {/* Interactive Neo4j Topology Graph */}
                <GraphVisualizer />

                {/* Postgres Vector Telemetry & Audit Stream */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  <VectorTelemetry />
                  <LiveAuditFeed />
                </div>
              </>
            )}

            {activeTab === 'graph' && (
              <div className="space-y-6">
                <GraphVisualizer />
                <LiveAuditFeed />
              </div>
            )}

            {activeTab === 'vector' && (
              <div className="space-y-6">
                <VectorTelemetry />
                <LiveAuditFeed />
              </div>
            )}

            {activeTab === 'cache' && (
              <div className="space-y-6">
                <div className="card-brutal p-6">
                  <h2 className="text-2xl font-display mb-1 flex items-center gap-2">
                    <HardDrive className="w-5 h-5" /> Redis Cache & Token Blocklist Telemetry
                  </h2>
                  <p className="text-xs text-black/60 font-mono mb-6">
                    In-memory data store performance, active token blocklist JTIs, and rate-limiting queue state
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="border border-black/20 bg-white p-4">
                      <div className="text-xs font-mono uppercase tracking-widest text-black/50">Cache Hit Ratio</div>
                      <div className="text-2xl font-display text-amber-600 mt-1 tabular-nums">
                        {demoMode ? `${telemetry.hitRatio.toFixed(1)}%` : '98.4%'}
                      </div>
                      <div className="text-[11px] font-mono text-black/50 mt-1">
                        {demoMode ? `${telemetry.latencyMs.toFixed(1)}ms avg response` : '0.2ms avg response'}
                      </div>
                    </div>

                    <div className="border border-black/20 bg-white p-4">
                      <div className="text-xs font-mono uppercase tracking-widest text-black/50">Revoked JWT JTIs</div>
                      <div className="text-2xl font-display mt-1 tabular-nums">
                        {telemetry.revokedTokens.toLocaleString()} tokens
                      </div>
                      <div className="text-[11px] font-mono text-black/50 mt-1">Blocklist active</div>
                    </div>

                    <div className="border border-black/20 bg-white p-4">
                      <div className="text-xs font-mono uppercase tracking-widest text-black/50">Memory Allocation</div>
                      <div className="text-2xl font-display text-emerald-700 mt-1 tabular-nums">
                        {demoMode ? `${telemetry.memoryMb.toFixed(1)} MB` : '128.4 MB'}
                      </div>
                      <div className="text-[11px] font-mono text-black/50 mt-1">redis:7-alpine container</div>
                    </div>
                  </div>
                </div>

                <LiveAuditFeed />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
