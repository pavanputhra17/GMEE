import React, { useEffect, useRef } from 'react';

/**
 * AsciiGlobe — SIGINT Observatory.
 *
 * An interactive 3D-projected ASCII globe rendered as monospace glyphs:
 *  - fbm-noise continents, Lambert shading, crimson scan ring + equator
 *  - blinking city lights on the night side (settlement clusters)
 *  - autonomous signal arcs: ◈ headed transmissions riding great circles,
 *    landing with an ASCII ripple on the destination
 *  - click anywhere = broadcast: a wide seismic ripple + 3 intercept arcs
 *    launch from the strike point, light flashes
 *  - dragging reveals the dotted graticule skeleton (parallels/meridians)
 *
 * Interaction: drag = rotate (yaw + pitch), fling = momentum decay,
 * hover = cursor light + crimson hotspot + live lat/long readout.
 * Logic steps at 120 updates/sec; paint capped by display refresh.
 */

/* ------------------------------ geometry ------------------------------ */

const POINT_COUNT = 2800;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const BASE_TILT = 0.38;
const TILT_MIN = -1.25;
const TILT_MAX = 1.25;
const BASE_REV_SEC = 48;
const LIGHT: readonly [number, number, number] = [-0.45, 0.55, 0.75];
const HOTSPOT_R = 72;
const DRAG_K_YAW = 0.005;
const DRAG_K_PITCH = 0.0038;
const FLING_MAX = 3.4;
const UPDATES_PER_SEC = 120;

const GLYPHS_LAND = ['·', ':', '-', '=', '+', '#', '@'] as const;
const GLYPH_SEA = '·';

interface GlobePoint {
  x: number; y: number; z: number;
  lat: number;
  land: boolean;
}

/** Tiny deterministic 3D value noise (hash lattice + trilinear smoothing). */
function makeNoise3d(seed: number) {
  const hash = (i: number, j: number, k: number): number => {
    let h = (i * 374761393 + j * 668265263 + k * 1442695041 + seed * 144665) | 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    h = h ^ (h >>> 16);
    return (h >>> 0) / 4294967295;
  };
  const smooth = (t: number) => t * t * (3 - 2 * t);
  return (x: number, y: number, z: number): number => {
    const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
    const xf = smooth(x - xi), yf = smooth(y - yi), zf = smooth(z - zi);
    let acc = 0;
    for (let dx = 0; dx <= 1; dx++) {
      for (let dy = 0; dy <= 1; dy++) {
        for (let dz = 0; dz <= 1; dz++) {
          const w =
            (dx ? xf : 1 - xf) * (dy ? yf : 1 - yf) * (dz ? zf : 1 - zf);
          acc += w * hash(xi + dx, yi + dy, zi + dz);
        }
      }
    }
    return acc;
  };
}

const noiseAt = makeNoise3d(1337);

function fbm(x: number, y: number, z: number): number {
  return (
    noiseAt(x * 1.6, y * 1.6, z * 1.6) * 0.6 +
    noiseAt(x * 3.4 + 11.3, y * 3.4 + 5.2, z * 3.4 + 7.7) * 0.28 +
    noiseAt(x * 7.1 + 27.1, y * 7.1 + 13.7, z * 7.1 + 3.3) * 0.12
  );
}

function stableRand(i: number): number {
  return ((Math.imul(i + 1, 2654435761) >>> 8) % 1024) / 1024;
}

function buildPoints(): GlobePoint[] {
  const pts: GlobePoint[] = [];
  for (let i = 0; i < POINT_COUNT; i++) {
    const y = 1 - (2 * (i + 0.5)) / POINT_COUNT;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const phi = i * GOLDEN_ANGLE;
    const x = r * Math.cos(phi);
    const z = r * Math.sin(phi);
    const lat = (Math.asin(y) * 180) / Math.PI;
    const n = fbm(x, y, z);
    const land = n > 0.54 || Math.abs(lat) > 78;
    pts.push({ x, y, z, lat, land });
  }
  return pts;
}

const POINTS = buildPoints();

/* ------------------------------- cities ------------------------------- */

interface City {
  x: number; y: number; z: number;
  lat: number; lon: number;
  big: boolean;
  phase: number;
}

function buildCities(): City[] {
  const landIdx: number[] = [];
  POINTS.forEach((p, i) => {
    if (p.land && Math.abs(p.lat) < 70) landIdx.push(i);
  });
  // deterministic pseudo-shuffle, then spread picks across the shuffle
  const shuffled = landIdx
    .map((i) => ({ i, k: (Math.imul(i + 91, 40503) >>> 7) % 9973 }))
    .sort((a, b) => a.k - b.k);
  const cities: City[] = [];
  const stepN = Math.max(1, Math.floor(shuffled.length / 16));
  for (let n = 0; n < shuffled.length && cities.length < 16; n += stepN) {
    const p = POINTS[shuffled[n].i];
    const lon = (Math.atan2(p.z, p.x) * 180) / Math.PI;
    cities.push({
      x: p.x, y: p.y, z: p.z,
      lat: p.lat, lon,
      big: stableRand(shuffled[n].i * 13 + 5) > 0.68,
      phase: stableRand(shuffled[n].i * 29 + 11) * Math.PI * 2,
    });
  }
  return cities;
}

const CITIES = buildCities();

/* ---------------------------- arcs & ripples --------------------------- */

type Vec3 = [number, number, number];

interface Arc {
  u: Vec3; v: Vec3;
  w: number; sinW: number;
  head: number;      // 0..1 progress of the bright head
  speed: number;     // head units per second
  trail: number;     // length behind head, same units
}

interface Ripple {
  c: Vec3;           // model-space centre (unit)
  ang: number;       // current angular radius, radians
  maxAng: number;
  speed: number;     // rad/s
  band: number;
  strength: number;  // 0..1
}

const slerp = (u: Vec3, v: Vec3, w: number, sinW: number, t: number): Vec3 => {
  const a = (Math.sin((1 - t) * w)) / sinW;
  const b = (Math.sin(t * w)) / sinW;
  return [
    u[0] * a + v[0] * b,
    u[1] * a + v[1] * b,
    u[2] * a + v[2] * b,
  ];
};

/* ------------------------------- component ----------------------------- */

export const AsciiGlobe: React.FC<{ className?: string }> = ({ className }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const coordRef = useRef<HTMLSpanElement>(null);
  const countRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    const coordEl = coordRef.current;
    const countEl = countRef.current;
    if (!canvas || !wrap || !coordEl || !countEl) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduced =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const styles = getComputedStyle(document.documentElement);
    const bone = styles.getPropertyValue('--hermes-bone').trim() || '#FFF7F2';
    const redBright =
      styles.getPropertyValue('--hermes-red-bright').trim() || '#E11D2E';
    const sea = '#B08A85';

    /* ------------------------------ state ------------------------------ */
    const st = {
      rotY: 0,
      pitch: BASE_TILT,
      yawVel: 0,
      dragging: false,
      downX: 0, downY: 0, downMs: 0,
      lastX: 0, lastY: 0, lastMoveMs: 0,
      hoverX: 0, hoverY: 0, hovering: false,
      lightCur: [...LIGHT] as Vec3,
      boost: 0,               // click flash 0..1
      wfAlpha: 0,             // graticule visibility 0..~0.16
      scanT: 12,
      seed: 7,
      nextArcIn: 1.6,         // seconds until next autonomous arc
      intercepts: 0,
    };
    const arcs: Arc[] = [];
    const ripples: Ripple[] = [];

    /* ------------------------------ sizing ----------------------------- */
    let W = 0, H = 0, dpr = 1;

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = Math.max(80, rect.width);
      H = Math.max(80, rect.height);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
    };
    resize();

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(resize);
      ro.observe(wrap);
    }

    /* --------------------------- projections --------------------------- */
    /** model-space unit vector -> view/screen */
    const project = (m: Vec3, cosA: number, sinA: number, cosT: number, sinT: number) => {
      const x1 = m[0] * cosA + m[2] * sinA;
      const z1 = -m[0] * sinA + m[2] * cosA;
      const y2 = m[1] * cosT - z1 * sinT;
      const z2 = m[1] * sinT + z1 * cosT;
      return { x1, y2, z2 };
    };

    const fmtLatLon = (lat: number, lon: number): string => {
      const ns = lat >= 0 ? 'N' : 'S';
      const ew = lon >= 0 ? 'E' : 'W';
      return `${Math.abs(lat).toFixed(1)}°${ns} ${Math.abs(lon).toFixed(1)}°${ew}`;
    };

    /** screen point -> {model unit vector, lat, lon} or null when missing disc */
    const pick = (px: number, py: number) => {
      const cx = W / 2, cy = H / 2;
      const R = Math.min(W, H) * 0.42;
      const vx = (px - cx) / R;
      const vy = -(py - cy) / R;
      const q = vx * vx + vy * vy;
      if (q > 1 || R <= 0) return null;
      const vz = Math.sqrt(1 - q);

      const cosT = Math.cos(st.pitch), sinT = Math.sin(st.pitch);
      const y1 = vy * cosT + vz * sinT;
      const z1 = -vy * sinT + vz * cosT;
      const cosA = Math.cos(st.rotY), sinA = Math.sin(st.rotY);
      const x0 = vx * cosA - z1 * sinA;
      const z0 = vx * sinA + z1 * cosA;

      const m: Vec3 = [x0, y1, z0];
      const lat = (Math.asin(Math.max(-1, Math.min(1, y1))) * 180) / Math.PI;
      const lon = (Math.atan2(z0, x0) * 180) / Math.PI;
      return { m, lat, lon };
    };

    const updateCoordBadge = () => {
      if (!st.hovering) {
        coordEl.style.opacity = '0';
        return;
      }
      const hit = pick(st.hoverX, st.hoverY);
      if (!hit) {
        coordEl.style.opacity = '0';
        return;
      }
      coordEl.textContent = fmtLatLon(hit.lat, hit.lon);
      coordEl.style.left = `${Math.min(st.hoverX + 14, W - 110)}px`;
      coordEl.style.top = `${Math.max(st.hoverY - 26, 6)}px`;
      coordEl.style.opacity = '1';
    };

    /* ------------------------- arc / fx spawning ----------------------- */
    const spawnArc = (from?: Vec3) => {
      let u: Vec3;
      if (from) u = from;
      else {
        const c = CITIES[Math.floor(stableRand(st.seed++ * 17) * CITIES.length) % CITIES.length];
        u = [c.x, c.y, c.z];
      }
      const c2 = CITIES[Math.floor(stableRand(st.seed++ * 23) * CITIES.length) % CITIES.length];
      const v: Vec3 = [c2.x, c2.y, c2.z];
      const dot = Math.max(-1, Math.min(1, u[0] * v[0] + u[1] * v[1] + u[2] * v[2]));
      const w = Math.acos(dot);
      if (w < 0.18) return; // too close to look like travel
      arcs.push({
        u, v, w,
        sinW: Math.sin(w),
        head: 0,
        speed: 0.32 + stableRand(st.seed++ * 31) * 0.14,
        trail: 0.3,
      });
    };

    const broadcast = (m: Vec3) => {
      ripples.push({ c: m, ang: 0.02, maxAng: 0.95, speed: 0.85, band: 0.07, strength: 0.85 });
      st.boost = 1;
      if (!reduced) {
        spawnArc(m);
        spawnArc(m);
        spawnArc(m);
      } else {
        st.intercepts += 1;
        paintCount();
      }
    };

    const paintCount = () => {
      countEl.textContent = `◉ ${st.intercepts} SIGNAL${st.intercepts === 1 ? '' : 'S'}`;
      countEl.style.color = redBright;
      window.setTimeout(() => {
        countEl.style.color = '';
      }, 420);
    };

    /* --------------------------- pointer UX ---------------------------- */
    canvas.style.cursor = 'grab';
    canvas.style.touchAction = 'none';

    const onPointerDown = (e: PointerEvent) => {
      st.dragging = true;
      st.downX = e.offsetX; st.downY = e.offsetY; st.downMs = performance.now();
      st.lastX = e.offsetX; st.lastY = e.offsetY; st.lastMoveMs = st.downMs;
      st.yawVel = 0;
      canvas.style.cursor = 'grabbing';
      canvas.setPointerCapture?.(e.pointerId);
    };

    const onPointerMove = (e: PointerEvent) => {
      st.hoverX = e.offsetX;
      st.hoverY = e.offsetY;
      st.hovering = true;

      if (st.dragging) {
        const nowMs = performance.now();
        const dtm = Math.max(8, nowMs - st.lastMoveMs) / 1000;
        const dx = e.offsetX - st.lastX;
        const dy = e.offsetY - st.lastY;

        const dYaw = dx * DRAG_K_YAW;
        st.rotY += dYaw;
        st.pitch = Math.max(TILT_MIN, Math.min(TILT_MAX, st.pitch + dy * DRAG_K_PITCH));

        const instV = dYaw / dtm;
        st.yawVel = st.yawVel * 0.72 + instV * 0.28;

        st.lastX = e.offsetX;
        st.lastY = e.offsetY;
        st.lastMoveMs = nowMs;
      }
      updateCoordBadge();
    };

    const endDrag = (e: PointerEvent) => {
      if (!st.dragging) return;
      st.dragging = false;
      canvas.style.cursor = 'grab';
      canvas.releasePointerCapture?.(e.pointerId);

      const moved = Math.hypot(e.offsetX - st.downX, e.offsetY - st.downY);
      const heldMs = performance.now() - st.downMs;
      if (moved < 6 && heldMs < 400) {
        // a click, not a drag → broadcast at the struck point
        const hit = pick(e.offsetX, e.offsetY);
        if (hit) broadcast(hit.m);
        st.yawVel = 0;
        return;
      }
      st.yawVel = Math.max(-FLING_MAX, Math.min(FLING_MAX, st.yawVel));
    };

    const onLeave = () => {
      st.hovering = false;
      updateCoordBadge();
    };

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);
    canvas.addEventListener('pointerleave', onLeave);

    /* ----------------------------- renderer ---------------------------- */
    const buckets = new Map<string, { glyph: string; color: string; pos: number[] }>();
    const push = (glyph: string, color: string, x: number, yy: number) => {
      const key = glyph + '\u0000' + color;
      let bkt = buckets.get(key);
      if (!bkt) {
        bkt = { glyph, color, pos: [] };
        buckets.set(key, bkt);
      }
      bkt.pos.push(x, yy);
    };

    const hexCache = new Map<string, string>();
    const rgba = (hex: string, a: number): string => {
      const key = hex + a.toFixed(3);
      let v = hexCache.get(key);
      if (v) return v;
      const h = hex.replace('#', '');
      const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
      v = `rgba(${parseInt(full.slice(0, 2), 16)}, ${parseInt(full.slice(2, 4), 16)}, ${parseInt(full.slice(4, 6), 16)}, ${a.toFixed(3)})`;
      hexCache.set(key, v);
      return v;
    };

    let raf = 0;
    let running = true;
    let last = 0;
    let acc = 0;

    const drawFrame = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) * 0.42;
      const fontSize = Math.max(9, Math.min(16, R / 22));
      ctx.font = `${fontSize}px "Courier Prime", ui-monospace, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const cosA = Math.cos(st.rotY), sinA = Math.sin(st.rotY);
      const cosT = Math.cos(st.pitch), sinT = Math.sin(st.pitch);

      /* light: cursor-follow on hover, eased */
      let lx: number, ly: number, lz: number;
      if (st.hovering) {
        lx = (st.hoverX - cx) / R;
        ly = -(st.hoverY - cy) / R;
        lz = 0.85;
        const ll = Math.hypot(lx, ly, lz) || 1;
        lx /= ll; ly /= ll; lz /= ll;
      } else {
        lx = LIGHT[0]; ly = LIGHT[1]; lz = LIGHT[2];
        const ll = Math.hypot(lx, ly, lz);
        lx /= ll; ly /= ll; lz /= ll;
      }
      const kL = 0.18;
      st.lightCur[0] += (lx - st.lightCur[0]) * kL;
      st.lightCur[1] += (ly - st.lightCur[1]) * kL;
      st.lightCur[2] += (lz - st.lightCur[2]) * kL;
      const Lx = st.lightCur[0], Ly = st.lightCur[1], Lz = st.lightCur[2];

      const scanLat = ((st.scanT * (180 / 14)) % 220) - 110;
      const hot2 = HOTSPOT_R * HOTSPOT_R;
      const boostMul = 1 + 0.5 * st.boost;

      buckets.clear();

      /* ---- base terrain ---- */
      for (let i = 0; i < POINTS.length; i++) {
        const p = POINTS[i];
        const pr = project([p.x, p.y, p.z], cosA, sinA, cosT, sinT);
        if (pr.z2 < 0.06) continue;

        const sx = cx + pr.x1 * R;
        const sy = cy - pr.y2 * R;
        const dLat = Math.abs(p.lat - scanLat);

        let inHot = false;
        if (st.hovering) {
          const hx = sx - st.hoverX;
          const hy = sy - st.hoverY;
          inHot = hx * hx + hy * hy < hot2 && pr.z2 > 0.12;
        }

        if (dLat < 4) {
          push('@', redBright, sx, sy);
          continue;
        }
        if (dLat < 13 && stableRand(i) < 0.35) {
          push(inHot ? '@' : p.land ? ':' : '·', inHot ? bone : redBright, sx, sy);
          continue;
        }
        if (Math.abs(p.lat) < 1.8) {
          push(inHot ? '@' : '=', inHot ? bone : redBright, sx, sy);
          continue;
        }

        const lam = Math.min(1, Math.max(0, pr.x1 * Lx + pr.y2 * Ly + pr.z2 * Lz) * boostMul);

        if (inHot) {
          push(p.land ? '@' : '+', redBright, sx, sy);
        } else if (p.land) {
          const idx = Math.min(GLYPHS_LAND.length - 1, Math.floor(lam * GLYPHS_LAND.length));
          push(GLYPHS_LAND[idx], rgba(bone, 0.28 + 0.72 * lam), sx, sy);
        } else {
          if (lam < 0.22) continue;
          push(GLYPH_SEA, rgba(sea, 0.18 + 0.4 * lam), sx, sy);
        }

        if (pr.z2 < 0.16 && Math.sin(st.scanT * 2.4 + i * 1.7) > 0.995) {
          push('+', rgba(redBright, 0.55), sx, sy);
        }
      }

      /* ---- city lights (night-side settlements) ---- */
      for (let ci = 0; ci < CITIES.length; ci++) {
        const c = CITIES[ci];
        const pr = project([c.x, c.y, c.z], cosA, sinA, cosT, sinT);
        if (pr.z2 < 0.04) continue;
        const sx = cx + pr.x1 * R;
        const sy = cy - pr.y2 * R;
        const twinkle = Math.sin(st.scanT * 1.8 + c.phase);
        if (twinkle < -0.35) continue;
        if (c.big) {
          push('*', rgba(redBright, 0.75 + 0.25 * twinkle), sx, sy);
          if (twinkle > 0.82) push('+', rgba(redBright, 0.5), sx + fontSize * 0.8, sy - fontSize * 0.5);
        } else {
          push(':', rgba(bone, 0.55 + 0.3 * twinkle), sx, sy);
        }
      }

      /* ---- graticule skeleton while manipulating ---- */
      if (st.wfAlpha > 0.012) {
        const wf = rgba(bone, st.wfAlpha);
        // parallels every 30°
        for (let la = -60; la <= 60; la += 30) {
          const rl = Math.cos((la * Math.PI) / 180);
          const yl = Math.sin((la * Math.PI) / 180);
          for (let lo = 0; lo < 360; lo += 5) {
            const lor = (lo * Math.PI) / 180;
            const pr = project([rl * Math.cos(lor), yl, rl * Math.sin(lor)], cosA, sinA, cosT, sinT);
            if (pr.z2 < 0.08) continue;
            push('·', wf, cx + pr.x1 * R, cy - pr.y2 * R);
          }
        }
        // meridians every 30°
        for (let lo = 0; lo < 360; lo += 30) {
          const lor = (lo * Math.PI) / 180;
          for (let la = -84; la <= 84; la += 6) {
            const lar = (la * Math.PI) / 180;
            const pr = project([
              Math.cos(lar) * Math.cos(lor),
              Math.sin(lar),
              Math.cos(lar) * Math.sin(lor),
            ], cosA, sinA, cosT, sinT);
            if (pr.z2 < 0.08) continue;
            push('·', wf, cx + pr.x1 * R, cy - pr.y2 * R);
          }
        }
      }

      /* ---- signal arcs ---- */
      for (let ai = arcs.length - 1; ai >= 0; ai--) {
        const arc = arcs[ai];
        const t0 = Math.max(0, arc.head - arc.trail);
        const t1 = Math.min(1, arc.head);
        const STEPS = 24;
        for (let si = 0; si <= STEPS; si++) {
          const tt = t0 + ((t1 - t0) * si) / STEPS;
          const m = slerp(arc.u, arc.v, arc.w, arc.sinW, tt);
          const elev = 1 + 0.24 * Math.sin(Math.PI * tt);
          const pr = project([m[0] * elev, m[1] * elev, m[2] * elev], cosA, sinA, cosT, sinT);
          if (pr.z2 < 0.02) continue; // hidden behind the planet
          const sx = cx + pr.x1 * R;
          const sy = cy - pr.y2 * R;
          if (si === STEPS && arc.head < 1) {
            push('◈', redBright, sx, sy);              // bright head
          } else {
            const age = (arc.head - tt) / arc.trail;   // 0 fresh … 1 oldest
            push(age < 0.33 ? '+' : '·', rgba(redBright, 0.75 * (1 - age)), sx, sy);
          }
        }
        if (arc.head >= 1) {
          // landed → ripple at the destination + intercept credit
          ripples.push({
            c: arc.v, ang: 0.02, maxAng: 0.42, speed: 0.55,
            band: 0.05, strength: 0.55,
          });
          st.intercepts += 1;
          paintCount();
          arcs.splice(ai, 1);
        }
      }

      /* ---- surface ripples ---- */
      for (let ri = ripples.length - 1; ri >= 0; ri--) {
        const rp = ripples[ri];
        for (let i = 0; i < POINTS.length; i += 2) {
          const p = POINTS[i];
          const dotP = p.x * rp.c[0] + p.y * rp.c[1] + p.z * rp.c[2];
          const angDist = Math.acos(Math.max(-1, Math.min(1, dotP)));
          const d = Math.abs(angDist - rp.ang);
          if (d > rp.band) continue;
          const pr = project([p.x, p.y, p.z], cosA, sinA, cosT, sinT);
          if (pr.z2 < 0.05) continue;
          const edge = 1 - d / rp.band;
          push('~', rgba(redBright, rp.strength * edge * (1 - rp.ang / rp.maxAng)), cx + pr.x1 * R, cy - pr.y2 * R);
        }
        if (rp.ang >= rp.maxAng) ripples.splice(ri, 1);
      }

      /* ---- halo rings ---- */
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(225, 29, 46, 0.45)';
      ctx.beginPath();
      ctx.arc(cx, cy, R + fontSize * 0.9, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(225, 29, 46, 0.14)';
      ctx.beginPath();
      ctx.arc(cx, cy, R + fontSize * 2.1, 0, Math.PI * 2);
      ctx.stroke();

      /* ---- cursor hotspot ring ---- */
      if (st.hovering) {
        ctx.strokeStyle = rgba(redBright, 0.4);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(st.hoverX, st.hoverY, HOTSPOT_R, 0, Math.PI * 2);
        ctx.stroke();
      }

      buckets.forEach((bkt) => {
        ctx.fillStyle = bkt.color;
        const arr = bkt.pos;
        for (let k = 0; k < arr.length; k += 2) {
          ctx.fillText(bkt.glyph, arr[k], arr[k + 1]);
        }
      });
    };

    /* ------------------------- simulation stepping -------------------- */
    const stepLogic = (dtStep: number) => {
      if (!reduced) st.scanT += dtStep;
      st.boost *= Math.exp(-3 * dtStep);

      // autonomous spin + fling decay
      if (!st.dragging) {
        const baseRate = reduced ? 0 : (2 * Math.PI) / BASE_REV_SEC;
        st.rotY += baseRate * dtStep + st.yawVel * dtStep;
        st.yawVel *= Math.exp(-2.4 * dtStep);
        if (Math.abs(st.yawVel) < 0.01) st.yawVel = 0;
      }

      // graticule alpha chases its target
      const wfTarget = st.dragging || Math.abs(st.yawVel) > 0.15 ? 0.16 : 0;
      st.wfAlpha += (wfTarget - st.wfAlpha) * Math.min(1, 8 * dtStep);

      // autonomous arc scheduler
      if (!reduced) {
        st.nextArcIn -= dtStep;
        if (st.nextArcIn <= 0) {
          spawnArc();
          st.nextArcIn = 2.8 + stableRand(st.seed++ * 41) * 2.6;
        }
      }

      // advance arcs & ripples
      for (let ai = 0; ai < arcs.length; ai++) {
        arcs[ai].head += arcs[ai].speed * dtStep;
      }
      for (let ri = 0; ri < ripples.length; ri++) {
        ripples[ri].ang += ripples[ri].speed * dtStep;
      }
    };

    const loop = (ms: number) => {
      try {
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

        if (advanced) drawFrame();
      } catch (err) {
        running = false;
        countEl.textContent = 'ERR: ' + String((err as Error)?.message ?? err).slice(0, 60);
        return;
      }
      raf = requestAnimationFrame(loop);
    };

    drawFrame(); // initial paint
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
      ro?.disconnect();
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', endDrag);
      canvas.removeEventListener('pointercancel', endDrag);
      canvas.removeEventListener('pointerleave', onLeave);
    };
  }, []);

  return (
    <div ref={wrapRef} className={className || 'relative'}>
      <canvas
        ref={canvasRef}
        className="block w-full h-full"
        aria-label="Interactive ASCII globe — drag to rotate, click to broadcast"
        role="img"
      />
      <span
        ref={coordRef}
        className="absolute z-20 pointer-events-none font-mono text-[10px] font-bold tracking-widest px-1.5 py-0.5 border border-hermes-red-bright/60 bg-hermes-ink/85 text-hermes-bone transition-opacity duration-150"
        style={{ opacity: 0 }}
      />
      <span
        ref={countRef}
        className="absolute z-20 bottom-2 right-2 font-mono text-[10px] font-bold tracking-widest text-hermes-bone/60 transition-colors duration-500 select-none"
      >
        ◉ 0 SIGNALS
      </span>
    </div>
  );
};
