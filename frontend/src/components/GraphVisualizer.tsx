import React, { useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Network, Info, ExternalLink, Orbit } from 'lucide-react';
import { corpusApi, StoryCluster } from '../api/corpus';
import { setSelectedArticle } from '../lib/useSelectedArticle';
import type { TabType } from './Header';

/**
 * GraphVisualizer — REAL story clusters from Neo4j.
 * Hub stories laid out as constellation centers; neighbors orbit them,
 * colored by outlet. Clicking a hub selects it; clicking a neighbor opens
 * the article. All nodes are genuine articles from the imported corpus.
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

const colorFor = (d?: string | null): string =>
  (d && OUTLET_COLORS[d]) || '#B08A85';

interface Node {
  id: string;
  title: string;
  domain: string;
  url: string;
  x: number;
  y: number;
  r: number;
  hub: boolean;
  score?: number;
}

/** Deterministic layout: hubs on a ring, neighbors in local clusters. */
function layout(clusters: StoryCluster[]): { nodes: Node[]; links: Array<{ a: string; b: string; s: number }> } {
  const W = 600, H = 400, CX = W / 2, CY = H / 2;
  const nodes: Node[] = [];
  const links: Array<{ a: string; b: string; s: number }> = [];
  const R = Math.min(W, H) * 0.34;

  clusters.forEach((c, ci) => {
    const ang = (ci / Math.max(1, clusters.length)) * Math.PI * 2 - Math.PI / 2;
    const hx = CX + Math.cos(ang) * R;
    const hy = CY + Math.sin(ang) * R * 0.82;

    nodes.push({
      id: c.id, title: c.title, domain: c.domain, url: c.url,
      x: hx, y: hy, r: 13, hub: true,
    });

    const nCount = c.neighbors.slice(0, 7);
    nCount.forEach((nb, ni) => {
      if (clusters.some((other) => other.id === nb.id)) return; // avoid dupes of other hubs
      const spread = ((ni + 1) / (nCount.length + 1)) * Math.PI * 1.35 + ang - 0.68 + ci * 0.35;
      const dist = 52 + (ni % 3) * 16;
      nodes.push({
        id: nb.id, title: nb.title, domain: nb.domain, url: nb.url,
        x: Math.max(30, Math.min(W - 30, hx + Math.cos(spread) * dist)),
        y: Math.max(26, Math.min(H - 26, hy + Math.sin(spread) * dist)),
        r: 7.5, hub: false, score: nb.score,
      });
      links.push({ a: c.id, b: nb.id, s: nb.score });
    });
  });
  return { nodes, links };
}

export const GraphVisualizer: React.FC<{ setActiveTab?: (tab: TabType) => void }> = ({ setActiveTab }) => {
  const [selected, setSelected] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const clusters = useQuery({
    queryKey: ['story-clusters'],
    queryFn: () => corpusApi.storyClusters(3, 5),
    refetchInterval: 30000,
  });

  const { nodes, links } = useMemo(
    () => layout(clusters.data?.clusters ?? []),
    [clusters.data]
  );
  const sel = nodes.find((n) => n.id === selected) ?? nodes.find((n) => n.hub) ?? null;

  return (
    <div className="card-brutal-dark p-6 flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-hermes-bone/12">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Network className="w-5 h-5" />
            <h2 className="text-2xl font-display">Story Cluster Topology</h2>
          </div>
          <p className="text-xs font-mono text-hermes-bone/55 uppercase tracking-wider">
            Live from Neo4j · {nodes.length} articles · {links.length} similarity edges
          </p>
        </div>
        <a
          href="http://localhost:7474"
          target="_blank"
          rel="noreferrer"
          className="chip-brutal bg-hermes-red text-hermes-bone border-hermes-red w-fit hover:bg-hermes-red-deep transition-colors"
        >
          Open Neo4j Browser <ExternalLink className="w-3 h-3 inline ml-1" />
        </a>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* SVG canvas */}
        <div className="lg:col-span-2 relative bg-hermes-panel-deep border border-hermes-bone/20 p-2 h-96 overflow-hidden rounded-none">
          {clusters.isLoading ? (
            <div className="shimmer h-full w-full" />
          ) : (
            <svg ref={svgRef} viewBox="0 0 600 400" className="w-full h-full">
              {links.map((l, i) => {
                const a = nodes.find((n) => n.id === l.a)!;
                const b = nodes.find((n) => n.id === l.b)!;
                if (!a || !b) return null;
                const hot =
                  selected === l.a || selected === l.b ||
                  (!selected && (a.hub || b.hub));
                return (
                  <line
                    key={i}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={hot ? '#E11D2E' : '#FFF7F2'}
                    strokeOpacity={selected ? (hot ? 0.85 : 0.12) : a.hub ? 0.45 : 0.25}
                    strokeWidth={hot ? 1.75 : 1}
                  />
                );
              })}
              {nodes.map((n) => (
                <g
                  key={n.id}
                  onClick={() => setSelected(n.id)}
                  className="cursor-pointer"
                >
                  {(sel?.id === n.id) && (
                    <circle cx={n.x} cy={n.y} r={n.r + 6} fill="none" stroke="#E11D2E" strokeWidth="1.5" />
                  )}
                  <circle
                    cx={n.x} cy={n.y} r={n.r}
                    fill={colorFor(n.domain)}
                    fillOpacity={n.hub ? 0.95 : 0.65}
                    stroke="#200A0E"
                    strokeWidth="1.25"
                  />
                  <title>{`${n.title}\n${n.domain}${n.score ? `\nsimilarity ${n.score}` : ''}`}</title>
                </g>
              ))}
            </svg>
          )}

          {/* Legend */}
          <div className="absolute bottom-2 left-2 bg-hermes-panel border border-hermes-bone/25 px-2.5 py-1.5 flex items-center gap-3 text-[10px] font-mono uppercase tracking-wider text-hermes-bone/70">
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 bg-hermes-red-bright" /> hub story</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-hermes-bone/60" /> similar coverage</span>
            <span className="hidden md:inline text-hermes-bone/40">click nodes · hover titles</span>
          </div>
        </div>

        {/* Inspector */}
        <div className="border border-hermes-bone/20 bg-hermes-panel p-5 flex flex-col justify-between">
          {sel ? (
            <>
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-hermes-bone/15 text-xs font-mono font-bold uppercase tracking-widest text-hermes-bone">
                  <span className="flex items-center gap-1.5">
                    <Info className="w-4 h-4" /> Article Telemetry
                  </span>
                  {sel.hub && (
                    <span className="chip-brutal bg-hermes-red-bright text-white border-hermes-red-bright">
                      HUB
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-display mt-3 mb-2 leading-snug">{sel.title}</h3>
                <span
                  className="chip-brutal w-fit mb-4"
                  style={{
                    borderColor: colorFor(sel.domain),
                    color: colorFor(sel.domain),
                  }}
                >
                  {sel.domain?.replace('www.', '')}
                </span>

                <div className="space-y-2.5 text-xs font-mono">
                  <div className="flex justify-between items-center bg-hermes-panel-deep border border-hermes-bone/20 p-2.5">
                    <span className="text-hermes-bone/55">Outlet</span>
                    <span className="font-bold" style={{ color: colorFor(sel.domain) }}>
                      {sel.domain?.replace('www.', '')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-hermes-panel-deep border border-hermes-bone/20 p-2.5">
                    <span className="text-hermes-bone/55">Similarity</span>
                    <span className="font-bold text-hermes-red-bright">
                      {sel.score ? `${(sel.score * 100).toFixed(1)}% match` : 'cluster center'}
                    </span>
                  </div>
                </div>
              </div>

              <a
                href={sel.url}
                target="_blank"
                rel="noreferrer"
                className="btn-brutal mt-4 w-fit"
              >
                Read original <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </>
          ) : (
            <p className="font-mono text-xs text-hermes-bone/50">Select a node…</p>
          )}

          {/* View in Timeline — always visible when a node is selected */}
          {sel && (
            <button
              onClick={() => {
                setSelectedArticle({
                  id: sel.id,
                  title: sel.title,
                  domain: sel.domain,
                });
                setActiveTab?.('timeline');
              }}
              className="btn-brutal w-fit mt-2"
            >
              View in Timeline <Orbit className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
