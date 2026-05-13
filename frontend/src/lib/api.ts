import type { AssessmentResult } from "./types";
import { generateMockResult } from "./mock";
import { isAbortError } from "./abortError";
import { speakReference } from "./recorder";

export type NativeAudioFetchOptions = {
  signal?: AbortSignal;
};

/** Optional abort for best-effort prewarm / native-audio prefetch. */
export type WarmPrefetchOptions = {
  signal?: AbortSignal;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const FORCE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";
const MAX_AUDIO_CACHE = 16;

const nativeAudioCache = new Map<string, Promise<Blob>>();

function remember<K, V>(map: Map<K, V>, key: K, value: V, max = MAX_AUDIO_CACHE): V {
  if (map.has(key)) map.delete(key);
  map.set(key, value);
  while (map.size > max) {
    const oldest = map.keys().next().value as K;
    map.delete(oldest);
  }
  return value;
}

export function isMockMode(): boolean {
  return FORCE_MOCK || !API_URL;
}

function mockScoreDelay(signal?: AbortSignal): Promise<void> {
  const ms = 900 + Math.random() * 600;
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const id = window.setTimeout(resolve, ms);
    const onAbort = () => {
      window.clearTimeout(id);
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export type ScoreRecordingOptions = {
  signal?: AbortSignal;
};

export async function scoreRecording(
  audioBlob: Blob,
  phraseText: string,
  accent: "GA" | "RP" = "GA",
  l1: string = "unknown",
  options?: ScoreRecordingOptions
): Promise<AssessmentResult> {
  const signal = options?.signal;
  if (isMockMode()) {
    await mockScoreDelay(signal);
    return generateMockResult(phraseText);
  }

  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  form.append("phrase", phraseText);
  form.append("accent", accent);
  form.append("l1", l1 || "unknown");

  const res = await fetch(`${API_URL}/api/score`, {
    method: "POST",
    body: form,
    signal,
  });

  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Scoring failed: ${msg}`);
  }

  return res.json() as Promise<AssessmentResult>;
}

/**
 * Play the phrase spoken in the target accent using Kokoro TTS from the backend.
 * Falls back to browser Web Speech API in mock mode.
 */
export async function playNativeAudio(
  text: string,
  accent: "GA" | "RP",
  speed: number = 0.9,
  opts?: NativeAudioFetchOptions
): Promise<void> {
  const signal = opts?.signal;
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  if (isMockMode()) {
    return speakReference(text, { signal });
  }

  let blob: Blob | null = null;
  try {
    blob = await getNativeAudio(text, accent, speed, signal);
  } catch (e) {
    if (isAbortError(e)) throw e;
    blob = null;
  }
  if (!blob) {
    return speakReference(text, { signal });
  }

  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);

  return new Promise((resolve, reject) => {
    let settled = false;
    const teardown = () => signal?.removeEventListener("abort", onAbort);

    const done = () => {
      if (settled) return;
      settled = true;
      teardown();
      URL.revokeObjectURL(audioUrl);
    };

    const onAbort = () => {
      try {
        audio.pause();
      } catch {}
      done();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort);

    audio.onended = () => {
      done();
      resolve();
    };
    audio.onerror = () => {
      done();
      resolve();
    };
    audio.play().catch(() => {
      done();
      resolve();
    });
  });
}

/**
 * Prepare a native-audio HTMLAudioElement plus per-word timings (estimated
 * proportionally to character count). Returns null in mock mode where we
 * fall back to the Web Speech API.
 */
export async function prepareNativeAudio(
  text: string,
  accent: "GA" | "RP",
  speed: number = 0.9,
  opts?: NativeAudioFetchOptions
): Promise<{ audio: HTMLAudioElement; words: { word: string; start_ms: number; end_ms: number }[] } | null> {
  if (isMockMode()) return null;
  const signal = opts?.signal;
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  let blob: Blob | null = null;
  try {
    blob = await getNativeAudio(text, accent, speed, signal);
  } catch (e) {
    if (isAbortError(e)) throw e;
    blob = null;
  }
  if (!blob) return null;
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  const cleanup = () => URL.revokeObjectURL(url);
  audio.addEventListener("ended", cleanup, { once: true });
  audio.addEventListener("error", cleanup, { once: true });
  const words = await estimateNativeWordTimings(text, audio);
  return { audio, words };
}

async function estimateNativeWordTimings(
  text: string,
  audio: HTMLAudioElement
): Promise<{ word: string; start_ms: number; end_ms: number }[]> {
  const tokens = text.match(/\S+/g) ?? [];
  if (tokens.length === 0) return [];
  const totalMs = await new Promise<number>((resolve) => {
    if (audio.readyState >= 1 && Number.isFinite(audio.duration) && audio.duration > 0) {
      resolve(audio.duration * 1000);
      return;
    }
    const onMeta = () => {
      audio.removeEventListener("loadedmetadata", onMeta);
      const dur = Number.isFinite(audio.duration) ? audio.duration * 1000 : tokens.length * 380;
      resolve(dur);
    };
    audio.addEventListener("loadedmetadata", onMeta);
    setTimeout(() => resolve(tokens.length * 380), 800);
  });
  const weights = tokens.map((t) => Math.max(1, t.replace(/[^A-Za-z]/g, "").length));
  const total = weights.reduce((s, w) => s + w, 0) || tokens.length;
  let cursor = 0;
  return tokens.map((word, i) => {
    const share = (weights[i] / total) * totalMs;
    const start = cursor;
    cursor = start + share;
    return { word, start_ms: Math.round(start), end_ms: Math.round(cursor) };
  });
}

function nativeAudioKey(text: string, accent: "GA" | "RP", speed: number): string {
  return `${accent}:${speed.toFixed(2)}:${text.trim().slice(0, 200)}`;
}

function getNativeAudio(
  text: string,
  accent: "GA" | "RP",
  speed: number,
  signal?: AbortSignal
): Promise<Blob> {
  const key = nativeAudioKey(text, accent, speed);
  const url = `${API_URL}/api/tts?text=${encodeURIComponent(text)}&accent=${accent}&speed=${speed}`;

  if (signal) {
    return fetch(url, { cache: "force-cache", signal })
      .then((res) => {
        if (!res.ok) throw new Error(`TTS failed (${res.status})`);
        return res.blob();
      })
      .then((blob) => {
        remember(nativeAudioCache, key, Promise.resolve(blob));
        return blob;
      });
  }

  const cached = nativeAudioCache.get(key);
  if (cached) return cached;

  const promise = fetch(url, { cache: "force-cache" })
    .then((res) => {
      if (!res.ok) throw new Error(`TTS failed (${res.status})`);
      return res.blob();
    })
    .catch((error) => {
      nativeAudioCache.delete(key);
      throw error;
    });
  return remember(nativeAudioCache, key, promise);
}

export function prefetchNativeAudio(
  text: string,
  accent: "GA" | "RP",
  speed: number = 0.9,
  opts?: WarmPrefetchOptions
): void {
  if (isMockMode() || !text.trim()) return;
  const signal = opts?.signal;
  getNativeAudio(text, accent, speed, signal).catch((e) => {
    if (isAbortError(e)) return;
    nativeAudioCache.delete(nativeAudioKey(text, accent, speed));
  });
}

export function prewarmPhrase(text: string, accent: "GA" | "RP", opts?: WarmPrefetchOptions): void {
  if (isMockMode() || !text.trim()) return;
  fetch(`${API_URL}/api/prewarm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phrase: text, accent }),
    keepalive: true,
    signal: opts?.signal,
  }).catch(() => {
    // Best-effort only; scoring still works without the warm cache.
  });
}
