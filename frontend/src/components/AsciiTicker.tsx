import React, { useEffect, useRef } from 'react';
import { useAnimationActivity } from '../lib/useAnimationActivity';

/**
 * AsciiTicker — a true character-crawl ticker.
 *
 * Not a CSS translate of a DOM strip: the message is one long character
 * string, and every logic step (120/sec) shifts which window of that string
 * is rendered into fixed monospace cells. Glyphs move cell-by-cell, exactly
 * like Cline's terminal hero. Logic runs at 120 updates/sec; requestAnimationFrame
 * applies steps in whole increments so a 60Hz display just shows 2 cells per
 * frame (no judder, no wasted paints). Pauses when the tab is hidden; renders
 * a static window under prefers-reduced-motion.
 */

const UPDATES_PER_SEC = 120;

interface AsciiTickerProps {
  items: string[];
  /** characters advanced per second */
  speed?: number;
  separator?: string;
  className?: string;
}

export const AsciiTicker: React.FC<AsciiTickerProps> = ({
  items,
  speed = 45,
  separator = '  ◆  ',
  className,
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const { animate } = useAnimationActivity(hostRef);

  useEffect(() => {
    const host = hostRef.current;
    const out = textRef.current;
    if (!host || !out) return;

    const reduced = !animate;

    const message = items.join(separator) + separator;

    /* ---- measure how many monospace chars fit the strip ---- */
    const probe = document.createElement('span');
    const style = getComputedStyle(out);
    probe.style.cssText = `position:absolute;visibility:hidden;white-space:pre;font:${style.font};letter-spacing:${style.letterSpacing}`;
    probe.textContent = 'M';
    host.appendChild(probe);
    const charW = Math.max(1, probe.getBoundingClientRect().width);
    host.removeChild(probe);

    const measure = () => Math.max(8, Math.floor(host.clientWidth / charW));
    let cols = measure();

    /* ---- build the repeating ring buffer (>= 2× viewport) ---- */
    let ring = message;
    while (ring.length < cols * 2) ring += message;

    let offset = 0; // fractional position, advances `speed` per second
    let raf = 0;
    let running = !reduced;
    let last = 0;
    let acc = 0;

    const renderWindow = () => {
      // right→left crawl: start slides forward through the ring
      const start = offset % ring.length;
      let view: string;
      if (start + cols <= ring.length) {
        view = ring.slice(start, start + cols);
      } else {
        view = ring.slice(start) + ring.slice(0, cols - (ring.length - start));
      }
      // paint segments: diamonds crimson, everything else inherits ink
      const frag = document.createDocumentFragment();
      const parts = view.split('◆');
      parts.forEach((part, i) => {
        if (i > 0) {
          const d = document.createElement('span');
          d.textContent = '◆';
          d.style.color = 'var(--hermes-red-bright)';
          frag.appendChild(d);
        }
        if (part) {
          const s = document.createElement('span');
          s.textContent = part;
          frag.appendChild(s);
        }
      });
      out.replaceChildren(frag);
    };

    const step = (dtSec: number) => {
      offset += speed * dtSec;
    };

    const loop = (ms: number) => {
      if (!running) return;
      if (last === 0) last = ms;
      let dt = (ms - last) / 1000;
      last = ms;
      if (dt > 0.25) dt = 0.25; // tab-switch spike guard

      // fixed 120Hz logic stepping — display refresh only caps paint rate
      acc += dt;
      const dtStep = 1 / UPDATES_PER_SEC;
      let stepped = false;
      while (acc >= dtStep) {
        step(dtStep);
        acc -= dtStep;
        stepped = true;
      }

      if (stepped) {
        // resize check is cheap; keeps cells correct through viewport changes
        const nowCols = measure();
        if (nowCols !== cols) {
          cols = nowCols;
          while (ring.length < cols * 2) ring += message;
        }
        renderWindow();
      }

      raf = requestAnimationFrame(loop);
    };

    renderWindow(); // paint initial frame immediately

    if (reduced) {
      return; // static window already rendered
    }

    raf = requestAnimationFrame(loop);
    const onVis = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        last = 0;
        raf = requestAnimationFrame(loop);
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      running = false;
      cancelAnimationFrame(raf);
    };
  }, [items, speed, separator, animate]);

  return (
    <div
      ref={hostRef}
      className={`overflow-hidden whitespace-pre select-none ${className ?? ''}`}
      role="marquee"
      aria-label={items.join(', ')}
    >
      <span ref={textRef} className="whitespace-pre" />
    </div>
  );
};
