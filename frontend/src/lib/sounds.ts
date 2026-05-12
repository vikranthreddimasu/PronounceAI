"use client";

/**
 * Tactile micro-sounds. Synthesized via WebAudio so we ship no audio assets.
 *
 * Three flavours:
 *   tap()        — soft pencil-tap, ~60ms. Default action.
 *   confirm()    — two-note rise. Score reveal / save.
 *   release()    — exhale, ~120ms. Stop recording / dismiss.
 *
 * Short, low-frequency cues — still “paper / studio” not arcade, but loud
 * enough to read on laptop speakers after `AudioContext` resume.
 *
 * User can mute via `setSoundsEnabled(false)`. Default = on.
 */

const KEY = "pronounceai.sounds.v1";

/** Linear gain multiplier on all peaks (was easy to miss on built‑in speakers). */
const LOUDNESS = 2.05;

let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (ctx) return ctx;
  const Ctx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return null;
  ctx = new Ctx();
  return ctx;
}

export function isSoundsEnabled(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(KEY);
  return raw !== "0";
}

export function setSoundsEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, enabled ? "1" : "0");
}

function envelope(
  c: AudioContext,
  osc: OscillatorNode,
  gain: GainNode,
  peak: number,
  attackMs: number,
  releaseMs: number
) {
  const now = c.currentTime;
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(peak, now + attackMs / 1000);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + (attackMs + releaseMs) / 1000);
  osc.start(now);
  osc.stop(now + (attackMs + releaseMs) / 1000 + 0.02);
}

/** Soft tap — used on most button presses. */
export function tap(): void {
  if (!isSoundsEnabled()) return;
  const c = getCtx();
  if (!c) return;
  const play = () => {
    // Mix of a low thud + a tiny click for "weight + crispness"
    const thud = c.createOscillator();
    const thudGain = c.createGain();
    thud.frequency.value = 180;
    thud.type = "sine";
    thud.connect(thudGain).connect(c.destination);
    envelope(c, thud, thudGain, 0.072 * LOUDNESS, 3, 52);

    const click = c.createOscillator();
    const clickGain = c.createGain();
    click.frequency.value = 1650;
    click.type = "triangle";
    click.connect(clickGain).connect(c.destination);
    envelope(c, click, clickGain, 0.022 * LOUDNESS, 0.8, 22);
  };
  if (c.state === "suspended") void c.resume().then(play).catch(() => {});
  else play();
}

/** Two-note rise — for score reveal / save success. */
export function confirm(): void {
  if (!isSoundsEnabled()) return;
  const c = getCtx();
  if (!c) return;
  const play = () => {
    const notes = [440, 660];
    notes.forEach((f, i) => {
      const o = c.createOscillator();
      const g = c.createGain();
      o.type = "sine";
      o.frequency.value = f;
      o.connect(g).connect(c.destination);
      const t0 = c.currentTime + i * 0.08;
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(0.055 * LOUDNESS, t0 + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.3);
      o.start(t0);
      o.stop(t0 + 0.36);
    });
  };
  if (c.state === "suspended") void c.resume().then(play).catch(() => {});
  else play();
}

/** Exhale — for stop / cancel / close. */
export function release(): void {
  if (!isSoundsEnabled()) return;
  const c = getCtx();
  if (!c) return;
  const play = () => {
    const noise = c.createBufferSource();
    const buf = c.createBuffer(1, c.sampleRate * 0.12, c.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) {
      const t = i / data.length;
      data[i] = (Math.random() * 2 - 1) * (1 - t) * 0.5;
    }
    noise.buffer = buf;
    const g = c.createGain();
    const filter = c.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 1100;
    noise.connect(filter).connect(g).connect(c.destination);
    const t0 = c.currentTime;
    g.gain.setValueAtTime(0.078 * LOUDNESS, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.12);
    noise.start(t0);
    noise.stop(t0 + 0.14);
  };
  if (c.state === "suspended") void c.resume().then(play).catch(() => {});
  else play();
}
