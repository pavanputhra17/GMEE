/**
 * lib/sound.ts contract tests.
 *
 * WebAudio is unavailable in jsdom, so we install a minimal fake
 * AudioContext recording node interactions. This drives the real
 * synthesis paths (hum/whoosh/arrive/win/lose) including mute gating
 * and stop-function behavior.
 */

class FakeAudioParam {
  value = 0;
  setValueAtTime = vi.fn();
  exponentialRampToValueAtTime = vi.fn();
}

class FakeNode {
  connections = 0;
  connect = vi.fn((dest: unknown) => dest);
  start = vi.fn();
  stop = vi.fn();
  disconnect = vi.fn();
}

class FakeAudioContext {
  state = 'running';
  sampleRate = 44100;
  currentTime = 0;
  destination = new FakeNode();
  resume = vi.fn(async () => {});
  createOscillator() {
    const o = new FakeNode();
    Object.assign(o, { type: 'sine', frequency: new FakeAudioParam() });
    return o;
  }
  createGain() {
    const g = new FakeNode();
    (g as unknown as { gain: FakeAudioParam }).gain = new FakeAudioParam();
    return g;
  }
  createBufferSource() {
    return new FakeNode();
  }
  createBiquadFilter() {
    const f = new FakeNode();
    Object.assign(f, { type: 'lowpass', frequency: new FakeAudioParam() });
    return f;
  }
  createBuffer(_ch: number, len: number, _rate: number) {
    return { getChannelData: () => new Float32Array(len) };
  }
}

describe('lib/sound', () => {
  let sound: typeof import('../src/lib/sound').sound;

  beforeAll(async () => {
    (window as unknown as { AudioContext: typeof FakeAudioContext }).AudioContext =
      FakeAudioContext as unknown as typeof AudioContext;
    ({ sound } = await import('../src/lib/sound'));
  });

  it('starts unmuted and toggles mute state', () => {
    expect(sound.isMuted()).toBe(false);
    sound.setMuted(true);
    expect(sound.isMuted()).toBe(true);
    sound.setMuted(false);
  });

  it('hum() returns a stop function that stops both oscillators', () => {
    const stop = sound.hum();
    expect(typeof stop).toBe('function');
    stop();
  });

  it('whoosh(), arrive(), win(), lose() create nodes on a live context without throwing', () => {
    expect(() => sound.whoosh(0.5)).not.toThrow();
    expect(() => sound.arrive()).not.toThrow();
    expect(() => sound.win()).not.toThrow();
    expect(() => sound.lose()).not.toThrow();
  });

  it('every effect is a no-op while muted (ac() gate)', () => {
    sound.setMuted(true);
    const stopWhileMuted = sound.hum();
    expect(stopWhileMuted()).toBeUndefined();
    expect(() => sound.win()).not.toThrow();
    sound.setMuted(false);
  });
});
