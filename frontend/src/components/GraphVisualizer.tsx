import React, { useState } from 'react';
import { Network, Info } from 'lucide-react';

interface Node {
  id: string;
  label: string;
  type: 'claim' | 'actor' | 'source' | 'bot';
  x: number;
  y: number;
  connections: string[];
  riskScore: number;
}

const mockNodes: Node[] = [
  { id: '1', label: 'Claim #4091: Deepfake Audio', type: 'claim', x: 200, y: 120, connections: ['2', '3', '5'], riskScore: 88 },
  { id: '2', label: 'Botnet Cluster B7', type: 'bot', x: 100, y: 220, connections: ['1', '4'], riskScore: 95 },
  { id: '3', label: 'Source Domain X', type: 'source', x: 340, y: 180, connections: ['1', '5', '6'], riskScore: 62 },
  { id: '4', label: 'Amplifier Node @viral', type: 'actor', x: 120, y: 340, connections: ['2'], riskScore: 78 },
  { id: '5', label: 'Claim #4092: Synthetic Video', type: 'claim', x: 420, y: 290, connections: ['1', '3', '6'], riskScore: 91 },
  { id: '6', label: 'Coordinated Disinfo Network', type: 'actor', x: 500, y: 150, connections: ['3', '5'], riskScore: 84 },
];

const TYPE_COLOR: Record<Node['type'], string> = {
  claim: '#C1121F',
  bot: '#0a0a14',
  source: '#6b7280',
  actor: '#374151'
};

export const GraphVisualizer: React.FC = () => {
  const [selectedNode, setSelectedNode] = useState<Node>(mockNodes[0]);
  const [activeFilter, setActiveFilter] = useState<'all' | 'claim' | 'actor'>('all');

  const filteredNodes = mockNodes.filter(node => {
    if (activeFilter === 'claim') return node.type === 'claim';
    if (activeFilter === 'actor') return node.type === 'actor' || node.type === 'bot';
    return true;
  });

  return (
    <div className="card-brutal p-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-black/15">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Network className="w-5 h-5" />
            <h2 className="text-2xl font-display">Neo4j Graph Topology Visualizer</h2>
          </div>
          <p className="text-xs font-mono text-black/60 uppercase tracking-wider">
            Claim propagation & coordinated disinformation cluster mapping
          </p>
        </div>

        {/* Graph Filters */}
        <div className="flex items-stretch border border-black/90 bg-white text-xs shadow-[2px_2px_0_0_rgba(10,10,20,1)]">
          <button
            onClick={() => setActiveFilter('all')}
            className={`px-3 py-1.5 font-mono uppercase tracking-wide transition-colors cursor-pointer ${
              activeFilter === 'all' ? 'bg-hermes-ink text-hermes-paper' : 'hover:bg-black/5'
            }`}
          >
            All Entities
          </button>
          <button
            onClick={() => setActiveFilter('claim')}
            className={`px-3 py-1.5 font-mono uppercase tracking-wide transition-colors cursor-pointer border-l border-black/90 ${
              activeFilter === 'claim' ? 'bg-hermes-ink text-hermes-paper' : 'hover:bg-black/5'
            }`}
          >
            Claims
          </button>
          <button
            onClick={() => setActiveFilter('actor')}
            className={`px-3 py-1.5 font-mono uppercase tracking-wide transition-colors cursor-pointer border-l border-black/90 ${
              activeFilter === 'actor' ? 'bg-hermes-ink text-hermes-paper' : 'hover:bg-black/5'
            }`}
          >
            Actors &amp; Bots
          </button>
        </div>
      </div>

      {/* Main Graph Area & Inspection Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* SVG Interactive Topology Screen */}
        <div className="lg:col-span-2 relative bg-white border border-black/40 p-4 h-80 flex items-center justify-center overflow-hidden group">
          {/* Subtle Grid Background */}
          <div className="absolute inset-0 grid-bg opacity-60 pointer-events-none" />

          {/* Empty state when filters hide every node */}
          {filteredNodes.length === 0 && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 text-center bg-white/85">
              <Network className="w-8 h-8 text-black/30" />
              <p className="text-xs font-mono text-black/50 uppercase tracking-widest">No entities match the active filter</p>
            </div>
          )}

          <svg className="w-full h-full relative z-10" viewBox="0 0 600 400">
            {/* Draw connection lines */}
            {filteredNodes.map(node =>
              node.connections.map(targetId => {
                const target = mockNodes.find(n => n.id === targetId);
                if (!target) return null;
                const isSelected = selectedNode.id === node.id || selectedNode.id === target.id;
                return (
                  <line
                    key={`${node.id}-${targetId}`}
                    x1={node.x}
                    y1={node.y}
                    x2={target.x}
                    y2={target.y}
                    stroke="#0a0a14"
                    strokeOpacity={isSelected ? 0.85 : 0.18}
                    strokeWidth={isSelected ? 1.75 : 1}
                  />
                );
              })
            )}

            {/* Draw Nodes */}
            {filteredNodes.map(node => {
              const isSelected = selectedNode.id === node.id;
              const color = TYPE_COLOR[node.type];

              return (
                <g
                  key={node.id}
                  onClick={() => setSelectedNode(node)}
                  className="cursor-pointer"
                >
                  {/* Selection ring */}
                  {isSelected && (
                    <>
                      <circle cx={node.x} cy={node.y} r="21" fill="none" stroke="#ffffff" strokeWidth="8" strokeOpacity="0.55" />
                      <circle cx={node.x} cy={node.y} r="21" fill="none" stroke="#0a0a14" strokeWidth="1.75" />
                    </>
                  )}
                  {/* High-risk halo — quiet rose, not brand red */}
                  {!isSelected && node.riskScore > 90 && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r="17"
                      fill="none"
                      stroke="#9f1239"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                      className="opacity-70 animate-pulse"
                    />
                  )}
                  {/* Node Circle — hard-edged with ink outline */}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={isSelected ? 15 : 12}
                    fill={color}
                    stroke="#0a0a14"
                    strokeWidth="1.5"
                    className="transition-all duration-200 hover:scale-110"
                    style={{ transformOrigin: `${node.x}px ${node.y}px` }}
                  />
                  {/* Node Label */}
                  <text
                    x={node.x}
                    y={node.y + 28}
                    textAnchor="middle"
                    fill="#0a0a14"
                    fontSize="10"
                    fontFamily="'Courier Prime', monospace"
                    className="select-none font-bold"
                    style={{ paintOrder: 'stroke', stroke: '#ffffff', strokeWidth: 3, strokeLinejoin: 'round' }}
                  >
                    {node.label.split(':')[0]}
                    {node.riskScore > 90 ? ' ⚠' : ''}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Legend */}
          <div className="absolute bottom-3 left-3 bg-white border border-black/90 px-3 py-1.5 flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-black/70 shadow-[2px_2px_0_0_rgba(10,10,20,1)]">
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-[#C1121F]" /> Claims</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-[#0a0a14]" /> Coordinated Bots</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-[#6b7280]" /> Sources</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 bg-[#374151]" /> Actors</span>
          </div>
        </div>

        {/* Selected Entity Inspector */}
        <div className="border border-black/90 bg-hermes-paper p-5 flex flex-col justify-between shadow-[4px_4px_0_0_rgba(10,10,20,1)]">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-black/15 text-xs font-mono font-bold uppercase tracking-widest text-hermes-ink">
              <span className="flex items-center gap-1.5">
                <Info className="w-4 h-4" /> Node Telemetry
              </span>
              <span>ID: #{selectedNode.id}</span>
            </div>

            <h3 className="text-xl font-display mt-3 mb-2">{selectedNode.label}</h3>
            <span className={`chip-brutal ${
              selectedNode.type === 'bot' ? 'bg-rose-100 text-rose-800' :
              selectedNode.type === 'source' ? 'bg-violet-100 text-violet-800' :
              selectedNode.type === 'actor' ? 'bg-teal-100 text-teal-800' :
              'bg-hermes-ink text-hermes-paper'
            }`}>
              Type: {selectedNode.type}
            </span>

            <div className="space-y-3 mt-4 text-xs font-mono">
              <div className="flex justify-between items-center bg-white border border-black/40 p-2.5">
                <span className="text-black/60">Viral Risk Score</span>
                <span className={`font-bold ${selectedNode.riskScore > 80 ? 'text-rose-700' : 'text-amber-600'}`}>
                  {selectedNode.riskScore} / 100
                </span>
              </div>

              <div className="flex justify-between items-center bg-white border border-black/40 p-2.5">
                <span className="text-black/60">Connected Neighbors</span>
                <span className="font-bold">{selectedNode.connections.length} edges</span>
              </div>

              <div className="flex justify-between items-center bg-white border border-black/40 p-2.5">
                <span className="text-black/60">Cypher Sync Latency</span>
                <span className="font-bold text-emerald-700">1.4ms (Bolt)</span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-black/15 flex items-center justify-between text-xs font-mono text-black/60">
            <span>Neo4j v5.20</span>
            <span className="flex items-center gap-1.5">
              <span className="pulse-dot pulse-dot-emerald scale-75" /> Live Session
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
