"use client";

/**
 * Local-only state store. No accounts, no server. The browser is the database.
 *
 * Buckets:
 *   profile        — user's target accent, L1, theme preference, onboarding flag
 *   sessions       — every completed assessment, newest first (capped to 200)
 *   phonemeStats   — per-phoneme rolling stats (attempts, avg gop)
 *   streak         — daily streak bookkeeping
 *
 * Mutators return the new value so the caller can update React state.
 */

import type { AssessmentResult, Accent } from "./types";

const KEY_PROFILE = "pronounceai.profile.v1";
const KEY_SESSIONS = "pronounceai.sessions.v1";
const KEY_PHONEMES = "pronounceai.phonemes.v1";
const KEY_STREAK = "pronounceai.streak.v1";

const MAX_SESSIONS = 200;

export type Theme = "light" | "dark" | "system";

export type UserProfile = {
  l1: string | null;
  targetAccent: Accent;
  theme: Theme;
  onboarded: boolean;
};

export const DEFAULT_PROFILE: UserProfile = {
  l1: null,
  targetAccent: "GA",
  theme: "light",
  onboarded: false,
};

export type Session = {
  id: string;
  date: number;
  phrase: string;
  mode: "phrases" | "free";
  accent: Accent;
  overall: number;
  scores: AssessmentResult["scores"];
  phonemeCount: number;
  worstPhoneme?: string;
};

export type PhonemeStat = {
  attempts: number;
  avgGop: number;
  lastSeen: number;
};

export type Streak = {
  current: number;
  longest: number;
  lastSessionDate: string | null;
};

/* ─────────────────  internals  ───────────────── */

function readJSON<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJSON<T>(key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new CustomEvent("paai:storage", { detail: { key } }));
  } catch {
    /* quota / private mode — silently degrade */
  }
}

/* ─────────────────  profile  ─────────────────── */

export function getProfile(): UserProfile {
  const p = readJSON<Partial<UserProfile>>(KEY_PROFILE, {});
  return { ...DEFAULT_PROFILE, ...p };
}

export function setProfile(patch: Partial<UserProfile>): UserProfile {
  const next = { ...getProfile(), ...patch };
  writeJSON(KEY_PROFILE, next);
  return next;
}

/* ─────────────────  sessions  ────────────────── */

export function getSessions(): Session[] {
  return readJSON<Session[]>(KEY_SESSIONS, []);
}

function pickWorstPhonemeIpa(r: AssessmentResult): string | undefined {
  const errs = r.phonemes.filter((p) => !p.correct);
  const pool = errs.length > 0 ? errs : r.phonemes;
  if (pool.length === 0) return undefined;
  let worst = pool[0];
  for (const p of pool) if (p.gop < worst.gop) worst = p;
  return worst.expected;
}

export function appendSession(
  result: AssessmentResult,
  meta: { phrase: string; mode: "phrases" | "free"; accent: Accent }
): Session {
  const session: Session = {
    id: `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
    date: Date.now(),
    phrase: meta.phrase,
    mode: meta.mode,
    accent: meta.accent,
    overall: result.overall,
    scores: result.scores,
    phonemeCount: result.phonemes.length,
    worstPhoneme: pickWorstPhonemeIpa(result),
  };
  const all = getSessions();
  const next = [session, ...all].slice(0, MAX_SESSIONS);
  writeJSON(KEY_SESSIONS, next);
  updatePhonemeStats(result);
  bumpStreak();
  return session;
}

export function clearSessions(): void {
  writeJSON(KEY_SESSIONS, []);
}

/* ─────────────────  phoneme stats  ───────────── */

export function getPhonemeStats(): Record<string, PhonemeStat> {
  return readJSON<Record<string, PhonemeStat>>(KEY_PHONEMES, {});
}

function updatePhonemeStats(result: AssessmentResult): void {
  const stats = getPhonemeStats();
  const now = Date.now();
  for (const p of result.phonemes) {
    const key = p.expected;
    const prev = stats[key] ?? { attempts: 0, avgGop: 0, lastSeen: 0 };
    const n = prev.attempts + 1;
    const avg = (prev.avgGop * prev.attempts + p.gop) / n;
    stats[key] = { attempts: n, avgGop: avg, lastSeen: now };
  }
  writeJSON(KEY_PHONEMES, stats);
}

export function clearPhonemeStats(): void {
  writeJSON(KEY_PHONEMES, {});
}

/** Map a phoneme's avg GOP to a 0..1 mastery score. */
export function masteryOf(stat: PhonemeStat | undefined): number {
  if (!stat || stat.attempts === 0) return 0;
  // GOP roughly ranges from -3.5 (bad) to 0 (perfect).
  const norm = Math.max(0, Math.min(1, (stat.avgGop + 3.0) / 3.0));
  // Squish single-attempt confidence
  const conf = 1 - Math.exp(-stat.attempts / 4);
  return norm * conf;
}

/* ─────────────────  streak  ──────────────────── */

function dateKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function getStreak(): Streak {
  return readJSON<Streak>(KEY_STREAK, { current: 0, longest: 0, lastSessionDate: null });
}

function bumpStreak(): Streak {
  const s = getStreak();
  const today = dateKey(new Date());
  if (s.lastSessionDate === today) return s;
  const yesterday = dateKey(new Date(Date.now() - 86_400_000));
  const next: Streak =
    s.lastSessionDate === yesterday
      ? { current: s.current + 1, longest: Math.max(s.longest, s.current + 1), lastSessionDate: today }
      : { current: 1, longest: Math.max(s.longest, 1), lastSessionDate: today };
  writeJSON(KEY_STREAK, next);
  return next;
}

/* ─────────────────  reset everything  ────────── */

export function resetAll(): void {
  if (typeof window === "undefined") return;
  [KEY_PROFILE, KEY_SESSIONS, KEY_PHONEMES, KEY_STREAK].forEach((k) =>
    window.localStorage.removeItem(k)
  );
  window.dispatchEvent(new CustomEvent("paai:storage", { detail: { key: "*" } }));
}

/* ─────────────────  React subscription helper  */

export function subscribeStorage(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onLocal = () => cb();
  const onStorage = (e: StorageEvent) => {
    if (!e.key || e.key.startsWith("pronounceai.")) cb();
  };
  window.addEventListener("paai:storage", onLocal);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("paai:storage", onLocal);
    window.removeEventListener("storage", onStorage);
  };
}
