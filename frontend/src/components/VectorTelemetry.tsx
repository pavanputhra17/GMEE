import React from 'react';
import { Database, Layers, Cpu, CheckCircle2, Zap } from 'lucide-react';

export const VectorTelemetry: React.FC = () => {
  return (
    <div className="card-brutal p-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-black/15">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Database className="w-5 h-5" />
            <h2 className="text-2xl font-display">
              PostgreSQL Vector Store
            </h2>
          </div>
          <p className="text-xs font-mono text-black/60 uppercase tracking-wider">
            Semantic claims embedding index · vector similarity metrics
          </p>
        </div>

        <span className="chip-brutal bg-hermes-ink text-hermes-paper border-black/90 w-fit">
          pgvector v0.7.0 / Postgres 16
        </span>
      </div>

      {/* Grid of Vector Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <VectorStatCard label="Embedding Model" value="bge-m3 / 1024-d" sub="Dense & Sparse Hybrid" icon={Layers} />
        <VectorStatCard label="Cosine Search Latency" value="4.2 ms" sub="HNSW Index (m=16, ef=64)" icon={Zap} />
        <VectorStatCard label="Indexed Claims" value="148,920" sub="+1,240 added today" icon={Database} />
        <VectorStatCard label="Index Build Status" value="100% Synced" sub="Zero pending re-indexing" icon={CheckCircle2} />
      </div>

      {/* Vector Similarity Search Interactive Test Preview */}
      <div className="border border-black/90 bg-hermes-paper p-5 flex flex-col gap-4">
        <h3 className="text-xs font-bold text-black font-mono uppercase tracking-widest flex items-center gap-2">
          <Cpu className="w-4 h-4" /> Nearest-Neighbor Query Simulation
        </h3>

        <div className="space-y-2 text-xs font-mono">
          <div className="flex items-center justify-between p-3 bg-white border border-black/40">
            <span className="text-black/80">Target Vector: [0.042, -0.891, 0.114, ...]</span>
            <span className="text-emerald-700 font-bold">Metric: Cosine</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
            <SimilarityResult title="Match 1 · Sim 0.962" text="Claim: 'Government shadow program altering atmospheric weather patterns'" distance="0.038" />
            <SimilarityResult title="Match 2 · Sim 0.894" text="Claim: 'Geoengineering aerosol deployments secretly documented'" distance="0.106" />
            <SimilarityResult title="Match 3 · Sim 0.821" text="Claim: 'Aviation contrail composition research paper analysis'" distance="0.179" />
          </div>
        </div>
      </div>
    </div>
  );
};

const VectorStatCard: React.FC<{
  label: string;
  value: string;
  sub: string;
  icon: React.ElementType;
}> = ({ label, value, sub, icon: Icon }) => {
  return (
    <div className="border border-black/90 bg-white p-4 flex flex-col justify-between card-brutal-hover">
      <div className="flex items-center justify-between text-black/50 mb-2">
        <span className="text-[10px] font-mono uppercase tracking-widest">{label}</span>
        <Icon className="w-4 h-4 text-hermes-ink" />
      </div>
      <div>
        <div className="text-xl font-display tabular-nums">{value}</div>
        <div className="text-[11px] font-mono text-black/50 mt-1">{sub}</div>
      </div>
    </div>
  );
};

const SimilarityResult: React.FC<{
  title: string;
  text: string;
  distance: string;
}> = ({ title, text, distance }) => {
  return (
    <div className="p-3 bg-white border border-black/40 flex flex-col justify-between">
      <div>
        <div className="font-bold text-[11px] mb-1 text-hermes-ink">{title}</div>
        <p className="text-black/70 text-[11px] line-clamp-2">{text}</p>
      </div>
      <div className="text-[10px] text-black/50 pt-2 mt-2 border-t border-black/15 flex justify-between font-mono">
        <span>Dist: {distance}</span>
        <span className="text-emerald-700 font-bold">Indexed</span>
      </div>
    </div>
  );
};
