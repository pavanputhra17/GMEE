import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Orbit, MousePointerClick, RotateCcw, X } from 'lucide-react';
import { timelineApi, TimelineCluster } from '../api/timeline';

import { useSelectedArticle, clearSelectedArticle } from '../lib/useSelectedArticle';
import { ClusterDossier } from './ClusterDossier';
import { usePollingPolicy } from '../lib/polling';
import { useAnimationActivity } from '../lib/useAnimationActivity';
import { QueryError } from './QueryError';
/**
 * TimelineTunnel — 3D story-time tunnel. Pure canvas projection, zero deps.
 *
 *   · Story clusters (linked cross-outlet coverage) float as rings in depth
 *   · NEWEST cluster floats on top (nearest), older ones recede below/away
 *   · CLICK the top ring → blackhole dive: you accelerate THROUGH it,
 *     screen fades through it, and you arrive facing the next-most-recent
 *   · MOUSE-WHEEL dives deeper / rises back up
 *   · Side rail lists the dive order; ESC or ↑ resets to surface
 *
 * Graph→timeline drill-down: when a story is selected in a graph tab
 * (useSelectedArticle), the tunnel fetches ONLY that story's connected
 * clusters (`?article_id=`) — diving still reads newest → oldest, ending
 * at the original first report. Motion rules honored: damped easing,
 * no jitter, reduced-motion respected.
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

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';

export default function TimelineTunnel(): React.ReactElement {
  const wrapRef = useRef<HTMLDivElement>(null);
  const cvRef = useRef<HTMLCanvasElement>(null);
  const { animate, reducedMotion, visible } = useAnimationActivity(wrapRef);
  const polling = usePollingPolicy(45000);
  const camRef = useRef({ z: -260 }); // camera depth into the tunnel (negative = before first ring)
  const targetRef = useRef({ z: -260 });
  const velRef = useRef(0);
  const divingRef = useRef(false);
  const flashRef = useRef(0);
  const starsRef = useRef<Array<{ x: number; y: number; z: number }>>([]);
  const mouseRef = useRef({ x: 0, y: 0 });
  const [depth, setDepth] = useState(0); // index of nearest cluster
  const depthRef = useRef(0); // mirrors `depth` for gesture math (no stale closures)
  const [inspect, setInspect] = useState<TimelineCluster | null>(null);

  // keep the gesture mirror in sync with every other depth setter
  // (rail buttons, keyboard, ring clicks, Surface reset)
  useEffect(() => {
    depthRef.current = depth;
  }, [depth]);

  // Graph→timeline drill-down: a story selected in a graph tab focuses the
  // tunnel on that story's connected clusters only (backend BFS ≤3 hops).
  const sel = useSelectedArticle();
  const selId = sel?.id ?? null;

  const q = useQuery({
    queryKey: ['timeline', selId ?? 'all'],
    queryFn: ({ signal }) => timelineApi.clusters(60, selId ?? undefined, { signal }),
    ...polling,
  });

  const clusters = useMemo(() => {
    const list = q.data?.clusters ?? [];
    // Ordering safety net: the tunnel dives to higher indices, so rings MUST
    // run newest-first (index 0 nearest = latest development, deepest =
    // original first report). Sort by the freshest time in each cluster.
    const t = (c: TimelineCluster) =>
      Date.parse(c.newest_member_at ?? c.published_at ?? '') || 0;
    return [...list].sort((a, b) => t(b) - t(a));
  }, [q.data]);

  // A fresh selection (or clearing it) re-anchors the dive: back to the
  // surface, facing the newest ring of the focused story.
  useEffect(() => {
    setDepth(0);
    depthRef.current = 0;
    divingRef.current = false;
    velRef.current = 0;
    camRef.current = { z: -260 };
    targetRef.current = { z: -260 };
  }, [selId]);

  // deterministic per-cluster layout around the tunnel axis
  const layout = useMemo(() => {
    return clusters.map((c, i) => ({
      c,
      z: i * 620, // depth spacing
      ox: ((i * 73) % 160 - 80), // gentle lateral drift per ring
      oy: ((i * 131) % 120 - 60),
      spin: (i % 2 === 0 ? 1 : -1) * (0.0004 + (i % 5) * 0.00012),
      seed: i * 17,
    }));
  }, [clusters]);

  // starfield init (dust rushing past during dive)
  useEffect(() => {
    starsRef.current = Array.from({ length: 420 }, (_, i) => ({
      x: Math.sin(i * 12.9898) * 1400,
      y: Math.cos(i * 78.233) * 900,
      z: (i * 137) % 34000,
    }));
  }, []);

  // keep camera target pinned to current top ring
  useEffect(() => {
    if (!layout.length) return;
    const d = Math.min(depth, layout.length - 1);
    targetRef.current.z = layout[d].z - 300; // stand slightly before the ring
  }, [depth, layout]);

  // wheel = dive / rise — but never a black hole for the page scroll
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || !layout.length) return;
    const onWheel = (e: WheelEvent) => {
      // Modified gestures (browser zoom, horizontal pan) belong to the page.
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      const from = depthRef.current;
      const next = Math.max(0, Math.min(layout.length - 1, from + (e.deltaY > 0 ? 1 : -1)));
      if (next === from) return;
      e.preventDefault();
      depthRef.current = next;
      setDepth(next);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [layout]);

  const onTimelineKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || inspect || !layout.length || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault();
      setDepth((value) => Math.max(0, Math.min(layout.length - 1, value + (event.key === 'ArrowDown' ? 1 : -1))));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (clusters[depth]) setInspect(clusters[depth]);
    }
  };

  // main render loop
  useEffect(() => {
    let raf = 0;
    const reduceMotion = reducedMotion;

    const project = (
      x: number, y: number, z: number,
      W: number, H: number, camZ: number
    ) => {
      const dz = z - camZ;
      if (dz <= 40) return null;
      const f = 620 / dz;
      return {
        sx: W / 2 + x * f + mouseRef.current.x * 18 * f,
        sy: H / 2 + y * f + mouseRef.current.y * 12 * f,
        f,
        dz,
      };
    };

    const drawRing = (
      ctx: CanvasRenderingContext2D,
      cx: number, cy: number, r: number,
      alpha: number, color: string, t: number, spin: number, seed: number,
      members: TimelineCluster['members']
    ) => {
      ctx.save();
      ctx.globalAlpha = alpha;
      // orbiting member nodes
      const n = members.length;
      for (let k = 0; k < n; k++) {
        const a = t * spin * 8 + (k / n) * Math.PI * 2 + seed * 0.37;
        const px = cx + Math.cos(a) * r;
        const py = cy + Math.sin(a) * r * 0.92;
        const rr = Math.max(1.4, 3.6 * alpha);
        ctx.beginPath();
        ctx.arc(px, py, rr, 0, Math.PI * 2);
        ctx.fillStyle = colorFor(members[k].domain);
        ctx.fill();
      }
      // hub core
      const pulse = reduceMotion ? 0 : Math.sin(t * 0.0016 + seed) * 0.08;
      ctx.beginPath();
      ctx.arc(cx, cy, r * (0.30 + pulse), 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = alpha * 0.9;
      ctx.fill();
      // rim
      ctx.beginPath();
      ctx.ellipse(cx, cy, r, r * 0.92, 0, 0, Math.PI * 2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4 * alpha + 0.2;
      ctx.globalAlpha = alpha * 0.55;
      ctx.stroke();
      ctx.restore();
    };

    const frame = (t: number) => {
      if (!visible) return;
      const cv = cvRef.current;
      const wrap = wrapRef.current;
      if (!cv || !wrap) return;
      const dpr = window.devicePixelRatio || 1;
      const W = wrap.clientWidth;
      const H = wrap.clientHeight;
      if (cv.width !== W * dpr || cv.height !== H * dpr) {
        cv.width = W * dpr;
        cv.height = H * dpr;
        cv.style.width = `${W}px`;
        cv.style.height = `${H}px`;
      }
      const ctx = cv.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // background — deep ink with vignette
      ctx.fillStyle = '#150508';
      ctx.fillRect(0, 0, W, H);
      const grad = ctx.createRadialGradient(W / 2, H / 2, H * 0.1, W / 2, H / 2, H * 0.85);
      grad.addColorStop(0, 'rgba(110,7,19,0.16)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);

      // camera physics — spring toward target, extra velocity while diving
      const cam = camRef.current;
      const tgt = targetRef.current.z;
      if (reduceMotion) {
        cam.z = tgt;
        divingRef.current = false;
        flashRef.current = 0;
      } else if (divingRef.current) {
        velRef.current += 26; // blackhole acceleration
        cam.z += velRef.current;
        if (cam.z >= tgt) {
          cam.z = tgt;
          velRef.current = 0;
          divingRef.current = false;
          flashRef.current = 1;
        }
      } else {
        cam.z += (tgt - cam.z) * 0.06;
      }

      // starfield dust
      ctx.fillStyle = 'rgba(255,247,242,0.5)';
      for (const s of starsRef.current) {
        const p = project(s.x * 0.4, s.y * 0.4, s.z, W, H, cam.z);
        if (!p) continue;
        const sz = Math.max(0.4, 1.6 * p.f);
        ctx.globalAlpha = Math.min(0.7, 0.25 * p.f);
        ctx.fillRect(p.sx, p.sy, sz, sz);
      }
      ctx.globalAlpha = 1;

      // rings — far to near so nearer rings paint over
      const sorted = [...layout].sort((a, b) => b.z - a.z);
      let nearestVisible: TimelineCluster | null = null;
      let nearestScreen: { x: number; y: number; r: number } | null = null;

      for (const L of sorted) {
        const p = project(L.ox, L.oy, L.z, W, H, cam.z);
        if (!p) continue;
        if (p.dz > 26000) continue;
        const fadeFar = Math.max(0, Math.min(1, (26000 - p.dz) / 6000));
        const fadeNear = Math.max(0, Math.min(1, (p.dz - 90) / 240));
        const alpha = fadeFar * fadeNear;
        if (alpha <= 0.02) continue;
        const r = Math.max(6, 130 * p.f);
        drawRing(ctx, p.sx, p.sy, r, alpha, colorFor(L.c.domain), reduceMotion ? 0 : t, L.spin, L.seed, L.c.members);

        // label for the nearest in-focus ring
        if (p.dz > 200 && p.dz < 1400 && !nearestVisible) {
          nearestVisible = L.c;
          nearestScreen = { x: p.sx, y: p.sy, r };
          ctx.save();
          ctx.font = `500 ${Math.max(11, Math.min(20, 15 * p.f))}px "Space Grotesk", serif`;
          ctx.textAlign = 'center';
          ctx.fillStyle = 'rgba(255,247,242,0.96)';
          ctx.shadowColor = '#000';
          ctx.shadowBlur = 8;
          const title = L.c.title.length > 74 ? L.c.title.slice(0, 71) + '…' : L.c.title;
          ctx.fillText(title, p.sx, p.sy - r - 14);
          ctx.font = '10px monospace';
          ctx.fillStyle = 'rgba(255,247,242,0.55)';
          ctx.fillText(
            `${fmtDate(L.c.published_at)} · ${L.c.deg} similarity links · ${L.c.domain?.replace('www.', '')}`,
            p.sx,
            p.sy - r + 4
          );
          ctx.restore();
        }
      }

      // blackhole pass-through flash
      if (flashRef.current > 0.01) {
        ctx.fillStyle = `rgba(255,247,242,${flashRef.current * 0.85})`;
        ctx.fillRect(0, 0, W, H);
        flashRef.current *= 0.88;
      }

      // HUD: depth meter
      ctx.fillStyle = 'rgba(255,247,242,0.5)';
      ctx.font = '10px monospace';
      ctx.fillText(`DEPTH ${String(depth).padStart(2, '0')} / ${layout.length}`, 14, H - 14);
      if (nearestVisible && !divingRef.current) {
        ctx.textAlign = 'right';
        ctx.fillText('CLICK RING TO DIVE ↓ · WHEEL TO DRIFT · ESC CLOSES PANEL', W - 14, H - 14);
        ctx.textAlign = 'left';
      }

      // store hit-target for click handling
      (cv as unknown as { __hit?: typeof nearestScreen }).__hit = nearestScreen;

      if (animate && layout.length > 0) raf = requestAnimationFrame(frame);
    };
    if (visible) raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [layout, depth, animate, reducedMotion, visible]);

  const onClickCanvas = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = (cvRef.current as unknown as { __hit?: { x: number; y: number; r: number } })?.__hit;
    if (hit) {
      const dx = mx - hit.x;
      const dy = my - hit.y;
      if (dx * dx + dy * dy <= (hit.r + 26) ** 2) {
        // dive into next cluster
        divingRef.current = true;
        velRef.current = 2;
        setDepth((d) => Math.min(Math.max(0, clusters.length - 1), d + 1));
        return;
      }
    }
    // otherwise open inspector for currently-focused cluster
    if (clusters[depth]) setInspect(clusters[depth]);
  };

  const resetSurface = () => {
    setDepth(0);
    divingRef.current = false;
    velRef.current = 0;
  };

  return (
    <div className="card-brutal-dark p-6 flex flex-col gap-5">
      {/* header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-4 border-b border-hermes-bone/12">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Orbit className="w-5 h-5" />
            <h2 className="text-2xl font-display">Story Time Tunnel</h2>
            {q.data && (
              <span className="chip-brutal border-hermes-red text-hermes-red-bright">
                {clusters.length} clusters · newest on top
              </span>
            )}
            {sel && (
              <span className="chip-brutal border-emerald-400/50 bg-emerald-400/10 text-emerald-300 flex items-center gap-1.5 max-w-[380px]">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
                <span className="truncate">
                  {sel.title.length > 48 ? sel.title.slice(0, 45) + '…' : sel.title}
                </span>
              </span>
            )}
          </div>
          <p className="text-xs font-mono text-hermes-bone/55 uppercase tracking-wider">
            click a story → fall through time into the next · wheel drifts deeper
            {sel ? ' · ends at the earliest linked coverage returned' : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {sel && (
            <button
              onClick={clearSelectedArticle}
              className="btn-ghost-brutal !py-1.5 !px-3 !text-hermes-bone !border-hermes-bone/30 w-fit"
              title="Show every story cluster again"
            >
              <X className="w-3.5 h-3.5" />
              All stories
            </button>
          )}
          <button disabled={!clusters.length} onClick={() => { if (clusters[depth]) setInspect(clusters[depth]); }} className="btn-brutal !py-1.5 !px-3">Inspect current story</button>
          <button onClick={resetSurface} className="btn-ghost-brutal !py-1.5 !px-3 !text-hermes-bone !border-hermes-bone/30 w-fit">
            <RotateCcw className="w-3.5 h-3.5" /> Surface
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
        {/* tunnel */}
        <div
          ref={wrapRef}
          role="region"
          aria-label="Interactive story timeline — arrow keys navigate, Enter inspects"
          tabIndex={0}
          onKeyDown={onTimelineKey}
          onClick={onClickCanvas}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            mouseRef.current = {
              x: (e.clientX - r.left - r.width / 2) / (r.width / 2),
              y: (e.clientY - r.top - r.height / 2) / (r.height / 2),
            };
          }}
          data-depth={depth}
          data-clusters={layout.length}
          className="relative bg-ink h-[620px] overflow-hidden cursor-pointer"
        >
          <canvas ref={cvRef} className="block" aria-hidden="true" />
          {q.isLoading && <p role="status" className="absolute inset-0 flex items-center justify-center text-xs font-mono">Loading story timeline…</p>}
          {q.isError && <div className="absolute inset-x-4 top-4"><QueryError title="Story timeline unavailable" error={q.error} onRetry={() => q.refetch()} retrying={q.isFetching} />
            {q.data && <p className="text-xs text-amber-300 mt-2">Last real timeline may be stale.</p>}
          </div>}
          {q.isSuccess && clusters.length === 0 && !sel && (
            <p className="absolute inset-0 flex items-center justify-center font-mono text-xs text-hermes-bone/50">
              No linked story clusters yet.
            </p>
          )}
          {q.isSuccess && clusters.length === 0 && sel && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
              <p className="font-mono text-xs text-hermes-bone/60 leading-relaxed max-w-sm">
                No linked coverage found for this story within 3 similarity hops.
                It may be too new to have cross-outlet links yet.
              </p>
              <button
                onClick={clearSelectedArticle}
                className="btn-ghost-brutal !py-1.5 !px-3 !text-hermes-bone !border-hermes-bone/30 w-fit"
              >
                <X className="w-3.5 h-3.5" />
                Back to all stories
              </button>
            </div>
          )}
        </div>

        {/* side rail — dive order */}
        <div className="border border-hermes-bone/15 bg-hermes-panel-deep p-4 h-[620px] overflow-y-auto scroll-contained">
          <div className="font-mono text-[10px] uppercase tracking-widest text-hermes-bone/45 mb-3 flex items-center gap-1.5">
            <MousePointerClick className="w-3.5 h-3.5" /> Dive order · newest first
          </div>
          <div className="space-y-1.5">
            {clusters.map((c, i) => (
              <button
                key={c.id}
                onClick={() => setDepth(i)}
                aria-current={i === depth ? 'step' : undefined}
                className={`w-full text-left px-3 py-2 border transition-colors ${
                  i === depth
                    ? 'border-hermes-red bg-hermes-red/10'
                    : i < depth
                      ? 'border-hermes-bone/10 opacity-45'
                      : 'border-hermes-bone/12 hover:border-hermes-bone/35'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[9px] uppercase tracking-wider text-hermes-bone/40">
                    {fmtDate(c.published_at)}
                  </span>
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ background: colorFor(c.domain) }}
                  />
                </div>
                <div className={`text-xs leading-snug mt-0.5 ${i === depth ? 'text-white font-medium' : 'text-hermes-bone/75'}`}>
                  {c.title.length > 66 ? c.title.slice(0, 63) + '…' : c.title}
                </div>
                <div className="font-mono text-[9px] text-hermes-bone/40 mt-0.5">
                  {c.deg} similarity links
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* inspector */}
      {inspect && (
        <ClusterDossier
          cluster={inspect}
          isFocused={sel?.id === inspect.id}
          onClose={() => setInspect(null)}
        />
      )}
    </div>
  );
}
