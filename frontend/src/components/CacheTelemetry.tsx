import React from 'react';
import { HardDrive } from 'lucide-react';
import { LiveAuditFeed } from './LiveAuditFeed';

interface CacheTelemetryProps {
  hitRatio?: string;
  latencyMs?: string;
  revokedTokens?: string;
  memoryMb?: string;
  simulated?: boolean;
}

/**
 * Redis queue / token-blocklist telemetry for the 'cache' tab.
 * Missing API metrics remain unknown; only an explicit simulator supplies
 * synthetic values.
 */
export const CacheTelemetry: React.FC<CacheTelemetryProps> = ({
  hitRatio,
  latencyMs,
  revokedTokens,
  memoryMb,
  simulated = false
}) => {
  return (
    <div className="space-y-6">
      <div className="card-brutal-dark p-6">
        <h2 className="text-2xl font-display mb-1 flex items-center gap-2">
          <HardDrive className="w-5 h-5" /> Redis Cache &amp; Token Blocklist Telemetry
        </h2>
        <p className="text-xs text-hermes-bone/55 font-mono mb-6">
          {simulated ? 'Explicit demo — all values below are simulated.' : 'Real dashboard snapshot. Unreported metrics are unknown, not zero.'}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-hermes-bone/20 bg-hermes-panel p-4">
            <div className="text-xs font-mono uppercase tracking-widest text-hermes-bone/50">Cache Hit Ratio</div>
            <div className="text-2xl font-display mt-1 tabular-nums">{hitRatio ?? 'Not reported'}</div>
            <div className="text-[11px] font-mono text-hermes-bone/50 mt-1">{latencyMs ? `${latencyMs} avg response` : 'Latency not reported by API'}</div>
          </div>

          <div className="border border-hermes-bone/20 bg-hermes-panel p-4">
            <div className="text-xs font-mono uppercase tracking-widest text-hermes-bone/50">Revoked JWT JTIs</div>
            <div className="text-2xl font-display mt-1 tabular-nums">{revokedTokens ?? 'Not reported'}</div>
            <div className="text-[11px] font-mono text-hermes-bone/50 mt-1">{revokedTokens ? 'Reported count' : 'No blocklist count supplied by API'}</div>
          </div>

          <div className="border border-hermes-bone/20 bg-hermes-panel p-4">
            <div className="text-xs font-mono uppercase tracking-widest text-hermes-bone/50">Memory Allocation</div>
            <div className="text-2xl font-display mt-1 tabular-nums">{memoryMb ?? 'Unavailable'}</div>
            <div className="text-[11px] font-mono text-hermes-bone/50 mt-1">{simulated ? 'Simulated allocation' : 'Redis memory from /dashboard'}</div>
          </div>
        </div>
      </div>

      <LiveAuditFeed />
    </div>
  );
};
