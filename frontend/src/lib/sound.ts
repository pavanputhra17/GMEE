/**
 * In-browser sound synthesis for the Masala Lab.
 *
 * Every effect is generated with the WebAudio API — no audio assets ship with
 * the bundle. All of them route through `ac()`, the single mute gate: it
 * returns `null` while muted (or when WebAudio is unavailable), which turns
 * each call into a cheap no-op and keeps the contract test's expectations
 * (no node creation while muted) honest.
 */

let muted = false;
let ctx: AudioContext | null = null;

type AudioContextCtor = new () => AudioContext;

const audioContextCtor = (): AudioContextCtor | null => {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    AudioContext?: AudioContextCtor;
    webkitAudioContext?: AudioContextCtor;
  };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
};

/** Mute gate. Returns the shared context, or `null` when sound is off. */
const ac = (): AudioContext | null => {
  if (muted) return null;
  const Ctor = audioContextCtor();
  if (!Ctor) return null;
  try {
    if (!ctx) ctx = new Ctor();
    if (ctx.state === 'suspended') void ctx.resume();
    return ctx;
  } catch {
    // Autoplay policy or a hostile environment: stay silent rather than throw.
    return null;
  }
};

/**
 * Attack/release envelope. Exponential ramps must stay non-zero, so the floor
 * is 0.0001 instead of 0.
 */
const envelope = (
  gain: GainNode,
  at: number,
  peak: number,
  attack: number,
  release: number,
): void => {
  const g = gain.gain;
  g.setValueAtTime(0.0001, at);
  g.exponentialRampToValueAtTime(peak, at + attack);
  g.exponentialRampToValueAtTime(0.0001, at + attack + release);
};

/** Fire-and-forget tone. */
const blip = (
  c: AudioContext,
  freq: number,
  at: number,
  dur: number,
  peak: number,
  type: OscillatorType = 'triangle',
): void => {
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, at);
  envelope(gain, at, peak, Math.min(0.03, dur / 3), dur);
  osc.connect(gain);
  gain.connect(c.destination);
  osc.start(at);
  osc.stop(at + dur + 0.05);
};

export const sound = {
  isMuted(): boolean {
    return muted;
  },

  setMuted(next: boolean): void {
    muted = next;
  },

  /**
   * Low drone: two detuned oscillators behind a slow low-pass sweep.
   * Returns the stop function (a no-op that returns undefined while muted).
   */
  hum(): () => void {
    const c = ac();
    if (!c) return () => undefined;

    const now = c.currentTime;

    const filter = c.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(420, now);
    filter.frequency.exponentialRampToValueAtTime(240, now + 3);

    const master = c.createGain();
    master.gain.setValueAtTime(0.0001, now);
    master.gain.exponentialRampToValueAtTime(0.045, now + 0.8);
    filter.connect(master);
    master.connect(c.destination);

    const oscillators = [55, 110.4].map((freq) => {
      const osc = c.createOscillator();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, now);
      osc.connect(filter);
      osc.start(now);
      return osc;
    });

    let stopped = false;
    return () => {
      if (stopped) return undefined;
      stopped = true;
      const at = c.currentTime;
      master.gain.setValueAtTime(0.045, at);
      master.gain.exponentialRampToValueAtTime(0.0001, at + 0.15);
      oscillators.forEach((osc) => osc.stop(at + 0.2));
      return undefined;
    };
  },

  /** Filtered noise sweep used for transitions. `rate` scales speed/pitch. */
  whoosh(rate = 1): void {
    const c = ac();
    if (!c) return;

    const speed = Math.max(0.25, Math.min(4, rate));
    const now = c.currentTime;
    const dur = 0.5 / speed;

    const buffer = c.createBuffer(1, Math.max(1, Math.floor(c.sampleRate * dur)), c.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;

    const noise = c.createBufferSource();
    noise.buffer = buffer;

    const sweep = c.createBiquadFilter();
    sweep.type = 'bandpass';
    sweep.frequency.setValueAtTime(1600 * speed, now);
    sweep.frequency.exponentialRampToValueAtTime(220, now + dur);

    const gain = c.createGain();
    envelope(gain, now, 0.3, 0.004, dur * 0.85);

    noise.connect(sweep);
    sweep.connect(gain);
    gain.connect(c.destination);
    noise.start(now);
    noise.stop(now + dur + 0.05);
  },

  /** Soft two-tone confirmation. */
  arrive(): void {
    const c = ac();
    if (!c) return;
    const now = c.currentTime;
    blip(c, 659.25, now, 0.16, 0.15);
    blip(c, 987.77, now + 0.09, 0.22, 0.11);
  },

  /** Ascending arpeggio. */
  win(): void {
    const c = ac();
    if (!c) return;
    const now = c.currentTime;
    [523.25, 659.25, 783.99, 1046.5].forEach((freq, i) => {
      blip(c, freq, now + i * 0.09, 0.3, 0.14);
    });
  },

  /** Descending two-note thud. */
  lose(): void {
    const c = ac();
    if (!c) return;
    const now = c.currentTime;
    blip(c, 311.13, now, 0.28, 0.13, 'sawtooth');
    blip(c, 196, now + 0.16, 0.42, 0.12, 'sawtooth');
  },
};

export default sound;
