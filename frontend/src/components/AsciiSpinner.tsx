import React, { useEffect, useRef, useState } from 'react';
import { useAnimationActivity } from '../lib/useAnimationActivity';

/**
 * AsciiSpinner — classic line spinner (| / - \) as a React component.
 *
 * Logic steps at 120 updates/sec; the visible glyph advances only when the
 * step counter crosses `advanceMs` (default 120ms) — readable terminal
 * cadence with buttery timing on any display. Renders a plain <span> so it
 * drops into any text flow. Static glyph under prefers-reduced-motion;
 * interval fully torn down when the tab is hidden.
 */

const UPDATES_PER_SEC = 120;

interface AsciiSpinnerProps {
  /** ms per visible glyph change */
  advanceMs?: number;
  className?: string;
  label?: string;
}

const FRAMES = ['|', '/', '-', '\\'] as const;

export const AsciiSpinner: React.FC<AsciiSpinnerProps> = ({
  advanceMs = 120,
  className,
  label = 'loading',
}) => {
  const hostRef = useRef<HTMLSpanElement>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const { animate } = useAnimationActivity(hostRef);

  useEffect(() => {
    const reduced = !animate;
    if (reduced) return; // keep the static first frame

    let raf = 0;
    let running = true;
    let last: number | null = null;
    let acc = 0;
    let elapsed = 0;

    const loop = (ms: number) => {
      if (!running) return;
      if (last === null) last = ms;
      let dt = (ms - last) / 1000;
      last = ms;
      if (dt > 0.25) dt = 0.25;

      acc += dt;
      elapsed += dt;
      const dtStep = 1 / UPDATES_PER_SEC;
      while (acc >= dtStep) acc -= dtStep; // burn 120Hz logic ticks

      // advance the glyph when elapsed crosses each advanceMs boundary
      const wantIdx = Math.floor((elapsed * 1000) / advanceMs) % FRAMES.length;
      setFrameIdx((prev) => (prev === wantIdx ? prev : wantIdx));

      raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    const onVis = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
        last = null;
      } else if (!running) {
        running = true;
        last = null;
        raf = requestAnimationFrame(loop);
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [advanceMs, animate]);

  void hostRef;
  void label;

  return (
    <span
      ref={hostRef}
      className={`inline-block ${className ?? ''}`}
      role="status"
      aria-label={label}
    >
      {FRAMES[frameIdx]}
    </span>
  );
};
