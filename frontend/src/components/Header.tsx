import React from 'react';
import { Activity, RefreshCw, Layers, Database, Network, HardDrive, FlaskConical } from 'lucide-react';

export type TabType = 'overview' | 'graph' | 'vector' | 'cache';

interface HeaderProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  refetchInterval: number;
  setRefetchInterval: (interval: number) => void;
  isFetching: boolean;
  onManualRefresh: () => void;
  status: 'ok' | 'degraded' | 'error';
  demoMode?: boolean;
}

const STATUS_STYLES = {
  ok: {
    dot: 'pulse-dot pulse-dot-emerald',
    badge: 'border-black/90 bg-white text-emerald-700',
    label: 'Systems Nominal'
  },
  degraded: {
    dot: 'pulse-dot pulse-dot-amber',
    badge: 'border-black/90 bg-white text-amber-700',
    label: 'Degraded State'
  },
  error: {
    dot: 'pulse-dot pulse-dot-rose',
    badge: 'border-black/90 bg-white text-rose-700',
    label: 'Connection Failed'
  }
} as const;

const TICKER_ITEMS = [
  'GMEE // GLOBAL MISINFORMATION EVOLUTION ENGINE',
  'REAL-TIME CLAIM PROPAGATION TELEMETRY',
  'PGVECTOR · NEO4J · REDIS',
  'V1.0'
];

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  refetchInterval,
  setRefetchInterval,
  isFetching,
  onManualRefresh,
  status,
  demoMode = false
}) => {
  const statusStyle = STATUS_STYLES[status];

  return (
    <header className="sticky top-0 z-40 -mx-4 md:-mx-8 lg:-mx-12 mb-8">
      <div className="bg-hermes-paper/95 backdrop-blur-sm border-b border-black/90">
        {/* Marquee ticker — Hermes-site signature */}
        <div className="overflow-hidden border-b border-black/20 bg-hermes-ink text-hermes-paper">
          <div className="marquee-track py-1">
            {[0, 1].map(dup => (
              <div key={dup} className="flex shrink-0 items-center" aria-hidden={dup === 1}>
                {TICKER_ITEMS.concat(TICKER_ITEMS).map((item, i) => (
                  <span
                    key={`${dup}-${i}`}
                    className="px-6 text-[10px] font-mono font-bold uppercase tracking-[0.2em] whitespace-nowrap"
                  >
                    {item} <span className="ml-6 opacity-60">◆</span>
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>

        <div className="px-4 md:px-8 lg:px-12 pt-5 flex flex-col gap-4">
          {/* Top Banner */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-black/15">
            <div className="flex items-center gap-4">
              <div className={`flex items-center justify-center w-12 h-12 border border-black/90 shadow-[3px_3px_0_0_rgba(10,10,20,1)] ${
                demoMode ? 'bg-hermes-yellow' : 'bg-hermes-ink'
              }`}>
                <Activity className={`w-6 h-6 ${demoMode ? 'text-black' : 'text-hermes-yellow'}`} />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-3xl md:text-4xl font-display leading-none">
                    GMEE
                  </h1>
                  {demoMode ? (
                    <span className="chip-brutal bg-hermes-yellow animate-pulse">
                      <FlaskConical className="w-3 h-3" />
                      Demo Telemetry
                    </span>
                  ) : (
                    <span className="chip-brutal bg-hermes-ink text-hermes-paper">v1.0 telemetry</span>
                  )}
                </div>
                <p className="text-xs font-mono uppercase tracking-widest text-black/60 mt-1">
                  Global Misinformation Evolution Engine
                </p>
              </div>
            </div>

            {/* Status + Controls */}
            <div className="flex flex-wrap items-center gap-3">
              <div className={`flex items-center gap-2 px-3 py-1.5 border text-xs font-semibold tracking-wide uppercase font-mono ${statusStyle.badge}`}>
                <span className={statusStyle.dot} />
                {statusStyle.label}
                {demoMode && <span className="ml-1 text-black/50 normal-case">(simulated)</span>}
              </div>

              {/* Polling interval dropdown */}
              <div className="flex items-center border border-black/90 bg-white p-0.5 text-xs">
                <select
                  value={refetchInterval}
                  onChange={(e) => setRefetchInterval(Number(e.target.value))}
                  className="bg-transparent text-black border-none outline-none py-1 pl-2 pr-1 font-mono cursor-pointer"
                >
                  <option value={2000}>2s live</option>
                  <option value={5000}>5s standard</option>
                  <option value={15000}>15s slow</option>
                  <option value={0}>Paused</option>
                </select>
              </div>

              {/* Manual refresh */}
              <button
                onClick={onManualRefresh}
                disabled={isFetching}
                className="btn-brutal !px-2.5 !py-2"
                title="Force Telemetry Sync"
              >
                <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Navigation Tabs — flat segmented control */}
          <nav className="flex items-center gap-0 overflow-x-auto">
            <TabButton id="overview" label="Overview Vitals" icon={Layers} activeTab={activeTab} setActiveTab={setActiveTab} />
            <TabButton id="graph" label="Neo4j Graph Engine" icon={Network} badge="7687" activeTab={activeTab} setActiveTab={setActiveTab} />
            <TabButton id="vector" label="Postgres Vector" icon={Database} badge="pgvector" activeTab={activeTab} setActiveTab={setActiveTab} />
            <TabButton id="cache" label="Redis Queue" icon={HardDrive} badge="6379" activeTab={activeTab} setActiveTab={setActiveTab} />
          </nav>
        </div>
      </div>
    </header>
  );
};

const TabButton: React.FC<{
  id: TabType;
  label: string;
  icon: React.ElementType;
  badge?: string;
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
}> = ({ id, label, icon: Icon, badge, activeTab, setActiveTab }) => {
  const isActive = activeTab === id;

  return (
    <button
      onClick={() => setActiveTab(id)}
      className={`flex items-center gap-2.5 px-4 py-2.5 text-xs md:text-sm font-mono font-bold uppercase tracking-wide transition-colors whitespace-nowrap cursor-pointer border-b-2 -mb-px ${
        isActive
          ? 'border-hermes-red text-hermes-ink bg-white'
          : 'border-transparent text-black/50 hover:text-black'
      }`}
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
      {badge && (
        <span className={`px-1.5 py-0.5 text-[10px] border ${
          isActive ? 'bg-hermes-ink text-hermes-paper border-hermes-red' : 'bg-black/5 text-black/50 border-black/20'
        }`}>
          {badge}
        </span>
      )}
    </button>
  );
};
