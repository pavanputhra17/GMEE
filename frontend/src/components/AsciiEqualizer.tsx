import React, { useEffect, useRef } from 'react';

/**
 * AsciiEqualizer — a strip of crimson data-bars rendered as stacked
 * monospace block glyphs (▁ ▂ ▃ ▄ ▅ ▆ ▇ █), dancing like piano keys as
 * telemetry flows. Values come from a smooth noise walk (deterministic,
 * calm); `pulse()` kicks every bar with an energy burst — call it when a
 * real event arrives. Logic steps at 120 updates/sec.
 *
 * Rendered as text (not canvas) so it stays crisp, selectable-free, and
 * themeable via CSS color.
 */

const UPDATES_PER_SEC = 120;
const BARS = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'] as const;

interface AsciiEqualizerProps {
  /** number of bars */
  count?: number;
  className?: string;
  label?: string;
}

/** Expose an imperative pulse() to the page: <AsciiEqualizer … ref/> style. */
const AsciiEqualizer: React.FC<AsciiEqualizerProps> = ({
  count = 48,
  className,
  label = 'telemetry equalizer',
}) => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // per-bar energy in [0,1]
    const energy = new Float32Array(count);
    const target = new Float32Array(count);
    const phase = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      phase[i] = ((Math.imul(i + 13, 2654435761) >>> 9) % 1000) / 1000 * Math.PI * 2;
      target[i] = 0.3 + ((Math.imul(i + 29, 40503) >>> 8) % 512) / 512 * 0.5;
      energy[i] = target[i];
    }

    let pulses: Array<{ at: number; power: number }> = [];
    (host as unknown as { __eqPulse?: (p?: number, x?: number) => void }).__eqPulse = (
      power = 1,
      x = -1
    ) => {
      const idx = x >= 0 ? Math.floor((x / host.clientWidth) * count) : Math.floor(Math.random() * count);
      pulses.push({ at: idx, power });
    };

    const barGlyph = (e: number) =>
      BARS[Math.min(BARS.length - 1, Math.floor(e * BARS.length))];

    const paint = () => {
      const frag = document.createDocumentFragment();
      for (let i = 0; i < count; i++) {
        const span = document.createElement('span');
        const e = energy[i];
        span.textContent = barGlyph(e);
        if (e > 0.82) {
          span.style.color = 'var(--hermes-red-bright)';
        } else if (e > 0.55) {
          span.style.color = 'var(--hermes-red)';
        } else {
          span.style.color = '';
        }
        frag.appendChild(span);
      }
      host.replaceChildren(frag);
    };

    paint(); // static first frame

    if (reduced) return;

    let raf = 0;
    let running = true;
    let last = 0;
    let acc = 0;
    let t = 0;

    const stepLogic = (dtStep: number) => {
      t += dtStep;

      // apply queued pulses as localised energy bursts
      if (pulses.length) {
        for (const p of pulses) {
          for (let d = -3; d <= 3; d++) {
            const i = p.at + d;
            if (i >= 0 && i < count) {
              energy[i] = Math.min(1, energy[i] + p.power * (1 - Math.abs(d) / 4));
            }
          }
        }
        pulses = [];
      }

      for (let i = 0; i < count; i++) {
        // slow noise walk toward the target, plus gentle wave
        const wave = 0.12 * Math.sin(t * 0.7 + phase[i]);
        energy[i] += (target[i] + wave - energy[i]) * Math.min(1, 2.2 * dtStep);
        energy[i] = Math.max(0.08, Math.min(1, energy[i]));
        target[i] += (((Math.sin(t * 0.23 + phase[i] * 1.7) + 1) / 2) - target[i]) * 0.35 * dtStep;
      }
    };

    const loop = (ms: number) => {
      if (!running) return;
      if (last === 0) last = ms;
      let dt = (ms - last) / 1000;
      last = ms;
      if (dt > 0.25) dt = 0.25;

      acc += dt;
      const dtStep = 1 / UPDATES_PER_SEC;
      let advanced = false;
      while (acc >= dtStep) {
        acc -= dtStep;
        advanced = true;
        stepLogic(dtStep);
      }

      if (advanced) paint();
      raf = requestAnimationFrame(loop);
    };

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
      delete (host as unknown as { __eqPulse?: unknown }).__eqPulse;
    };
  }, [count]);

  void label;

  // nowrap + overflow-hidden: the bar strip is decorative, so it clips to
  // its band instead of widening the page (it used to add ~640px of
  // horizontal scroll at phone widths).
  return (
    <div
      ref={hostRef}
      role="img"
      aria-label={label}
      className={`font-mono leading-none tracking-[0.1em] select-none whitespace-nowrap overflow-hidden ${className ?? ''}`}
    />
  );
};

export default AsciiEqualizer;
