import React, { useState, useEffect } from 'react';
import { Terminal } from 'lucide-react';

interface AuditLog {
  id: string;
  timestamp: string;
  type: 'info' | 'success' | 'warn';
  source: 'POSTGRES' | 'NEO4J' | 'REDIS' | 'LLM_PIPELINE' | 'HEALTHCHECK';
  message: string;
}

const initialLogs: AuditLog[] = [
  { id: '1', timestamp: '10:14:02.102', type: 'success', source: 'HEALTHCHECK', message: 'GET /health/ready poll returned HTTP 200 OK' },
  { id: '2', timestamp: '10:14:01.890', type: 'success', source: 'NEO4J', message: 'Cypher UNWIND batch synchronized 42 nodes & 118 edges' },
  { id: '3', timestamp: '10:14:00.412', type: 'info', source: 'POSTGRES', message: 'HNSW vector index query completed in 4.18ms' },
  { id: '4', timestamp: '10:13:58.700', type: 'success', source: 'LLM_PIPELINE', message: 'Claude API factual claim extraction structured output verified' },
  { id: '5', timestamp: '10:13:55.120', type: 'warn', source: 'REDIS', message: 'Rate-limit window near threshold for bearer token (82% capacity)' },
];

const TYPE_STYLES = {
  info: {
    border: 'border-l-hermes-ink',
    dot: 'bg-hermes-ink'
  },
  success: {
    border: 'border-l-emerald-600',
    dot: 'bg-emerald-600'
  },
  warn: {
    border: 'border-l-amber-500',
    dot: 'bg-amber-500'
  }
} as const;

export const LiveAuditFeed: React.FC = () => {
  const [logs, setLogs] = useState<AuditLog[]>(initialLogs);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = new Date().toLocaleTimeString('en-US', { hour12: false }) + '.' + Math.floor(Math.random() * 900 + 100);
      const sources: AuditLog['source'][] = ['POSTGRES', 'NEO4J', 'REDIS', 'LLM_PIPELINE', 'HEALTHCHECK'];
      const randomSource = sources[Math.floor(Math.random() * sources.length)];
      const roll = Math.random();
      const type: AuditLog['type'] = roll > 0.85 ? 'warn' : roll > 0.45 ? 'success' : 'info';

      const newLog: AuditLog = {
        id: Date.now().toString(),
        timestamp: now,
        type,
        source: randomSource,
        message: getMockMessage(randomSource)
      };

      setLogs(prev => [newLog, ...prev.slice(0, 14)]);
    }, 9000); // one calm entry every 9s instead of constant churn

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="card-brutal p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between pb-3 border-b border-black/15">
        <div className="flex items-center gap-2">
          <Terminal className="w-5 h-5" />
          <h2 className="text-2xl font-display">Live Telemetry Audit Stream</h2>
        </div>

        <div className="flex items-center gap-2">
          <span className="pulse-dot pulse-dot-emerald scale-75" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-black/60">Streaming Feed</span>
        </div>
      </div>

      {/* Terminal window — ink header bar */}
      <div className="border border-black/90">
        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-hermes-ink border-b border-black/90">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-600" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="ml-2 text-[10px] font-mono uppercase tracking-widest text-white/70">gmee://audit-stream</span>
        </div>

        <div className="bg-white p-3 font-mono text-xs max-h-72 overflow-y-auto space-y-1">
          {logs.map((log, index) => (
            <div
              key={log.id}
              className={`flex items-start gap-3 p-1.5 pl-2.5 border-l-2 border-b border-b-black/5 last:border-b-0 hover:bg-hermes-paper transition-colors ${TYPE_STYLES[log.type].border} ${index === 0 ? 'feed-enter' : ''}`}
            >
              <span className={`mt-1.5 w-1.5 h-1.5 shrink-0 ${TYPE_STYLES[log.type].dot}`} />
              <span className="text-black/40 whitespace-nowrap text-[11px] tabular-nums">{log.timestamp}</span>
              <span className={`px-1.5 py-0.5 text-[10px] font-bold whitespace-nowrap border ${
                log.source === 'POSTGRES' ? 'bg-violet-100 text-violet-800 border-violet-800/40' :
                log.source === 'NEO4J' ? 'bg-hermes-ink text-hermes-paper border-hermes-ink' :
                log.source === 'REDIS' ? 'bg-amber-100 text-amber-800 border-amber-800/40' :
                log.source === 'LLM_PIPELINE' ? 'bg-teal-100 text-teal-800 border-teal-800/40' :
                'bg-black/5 text-black/60 border-black/20'
              }`}>
                {log.source}
              </span>
              <span className="text-black/80 flex-1 leading-relaxed">{log.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

function getMockMessage(source: AuditLog['source']): string {
  switch (source) {
    case 'POSTGRES':
      return `Executed vector cosine distance search against claims_v2 (0.${Math.floor(Math.random() * 8 + 2)}ms)`;
    case 'NEO4J':
      return `Updated graph node edge weights for ${Math.floor(Math.random() * 20 + 5)} claim relationships`;
    case 'REDIS':
      return `Rate-limiting window evaluated for API bearer token (0.2ms latency)`;
    case 'LLM_PIPELINE':
      return `Fact-check extraction verified across ${Math.floor(Math.random() * 5 + 1)} incoming claims`;
    case 'HEALTHCHECK':
      return `System health probe OK: all 3 services responding nominally`;
  }
}
