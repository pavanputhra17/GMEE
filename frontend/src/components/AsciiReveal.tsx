import React, { useEffect, useRef } from 'react';

/**
 * AsciiReveal — scroll-triggered glyph-dissolve curtain.
 *
 * When the wrapped section scrolls into view, a monospace noise field
 * (░ ▒ ▓ ·) painted on an absolutely-positioned canvas dissolves away over
 * `durationMs` (default 450), uncovering the real content beneath. Logic
 * steps at 120 updates/sec; each logic tick recomputes every cell's
 * threshold against progress, so cells pop in deterministic order while the
 * field still reads as organic noise. One-shot per mount; static (curtain
 * already gone) under prefers-reduced-motion; animation pauses when hidden.
 */

const UPDATES_PER_SEC = 120;
const GLYPHS = ['░', '▒', '▓', '·'] as const;

interface AsciiRevealProps {
  children: React.ReactNode;
  className?: string;
  durationMs?: number;
}

export const AsciiReveal: React.FC<AsciiRevealProps> = ({
  children,
  className,
  durationMs = 450,
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let W = 0, H = 0, dpr = 1;
    let cols = 0, rows = 0, cell = 14;
    let thresholds: Float32Array = new Float32Array(0);
    // per-cell stable pseudo-random in [0,1) — deterministic dissolve order
    const randAt = (i: number) => ((Math.imul(i + 7, 2654435761) >>> 9) % 1000) / 1000;

    const layout = () => {
      const rect = host.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = Math.max(40, rect.width);
      H = Math.max(40, rect.height);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      cell = 14;
      cols = Math.ceil(W / cell);
      rows = Math.ceil(H / cell);
      thresholds = new Float32Array(cols * rows);
      for (let i = 0; i < thresholds.length; i++) thresholds[i] = randAt(i);

      ctx.font = '11px "Courier Prime", ui-monospace, monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
    };
    layout();

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(layout);
      ro.observe(host);
    }

    /* -------- curtain painting -------- */
    let raf = 0;
    let running = false;
    let started = false;
    let done = false;
    let startMs = 0;
    let lastProgress = -1;

    const paintCurtain = (progress: number) => {
      ctx.clearRect(0, 0, W, H);
      if (progress >= 1) return;

      // global alpha fades the whole field toward the end…
      const fadeAll = progress > 0.72 ? 1 - (progress - 0.72) / 0.28 : 1;

      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          const i = r * cols + c;
          const th = thresholds[i];
          if (th < progress) continue; // this cell has dissolved

          // glyph gets sparser as its local threshold approaches…
          const local = (th - progress) / Math.max(0.001, 1 - progress);
          const gi =
            local > 0.66 ? GLYPHS[2] : local > 0.4 ? GLYPHS[1] : local > 0.15 ? GLYPHS[0] : GLYPHS[3];

          ctx.globalAlpha = 0.5 * fadeAll;
          ctx.fillStyle = '#E7C9C4'; // rose paper — matches landing canvas
          ctx.fillText(gi, c * cell + cell / 2, r * cell + cell / 2);
        }
      }
      ctx.globalAlpha = 1;
    };

    const clearCurtain = () => {
      ctx.clearRect(0, 0, W, H);
      canvas.style.pointerEvents = 'none';
    };

    const loop = (ms: number) => {
      if (!running) return;
      if (!startMs) startMs = ms;
      let dt = ms - startMs;
      if (dt > 2000) dt = 2000;

      // 120Hz fixed-step accumulation for smooth progress
      const p = Math.min(1, dt / durationMs);
      const stepped = Math.floor(p * UPDATES_PER_SEC * (durationMs / 1000));
      void stepped;

      if (p !== lastProgress) {
        lastProgress = p;
        paintCurtain(p);
      }

      if (p >= 1) {
        done = true;
        running = false;
        clearCurtain();
        return;
      }
      raf = requestAnimationFrame(loop);
    };

    const startDissolve = () => {
      if (started) return;
      started = true;
      if (reduced) {
        done = true;
        clearCurtain();
        return;
      }
      running = true;
      raf = requestAnimationFrame(loop);
    };

    /* -------- one-shot IntersectionObserver trigger -------- */
    if (!('IntersectionObserver' in window)) {
      clearCurtain(); // ancient browsers just get content immediately
      done = true;
    } else {
      const io = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            io.disconnect();
            startDissolve();
          }
        },
        { threshold: 0.12 }
      );
      io.observe(host);
    }

    const onVis = () => {
      if (!started || done) return;
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        startMs = 0;
        raf = requestAnimationFrame(loop);
      }
    };
    document.addEventListener('visibilitychange', onVis);

    return () => {
      document.removeEventListener('visibilitychange', onVis);
      running = false;
      cancelAnimationFrame(raf);
      ro?.disconnect();
    };
  }, [durationMs]);

  return (
    <div ref={hostRef} className={`relative ${className ?? ''}`}>
      {children}
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="absolute inset-0 z-10 pointer-events-none"
      />
    </div>
  );
};
