"use client";

import { isAbortError } from "./abortError";

/**
 * Voice profile = multi-take enrollment store, persisted server-side as
 * `data/enrollments/<userId>/take_NNN.wav` and bundled into a single 24kHz
 * reference clip (≤28s) that CosyVoice 3 ingests directly.
 *
 * The browser holds only an opaque UUID handle in localStorage so the
 * backend can look up the user's takes. No accounts, no PII.
 */

const STORAGE_KEY = "pronounceai.voice_id";
const VOICE_EVENT = "paai:voice-session";
const API_URL = process.env.NEXT_PUBLIC_API_URL;
const FORCE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";
const MAX_VOICE_CLIP_CACHE = 8;

const voiceClipCache = new Map<string, Promise<SpokenClip>>();
const knownVoiceRevisions = new Map<string, string>();

export type VoiceSessionStatus = "loading" | "none" | "ready" | "error";
export type VoiceRenderMode = "target_accent" | "natural";
export type VoiceEmotion =
  | "neutral"
  | "happy"
  | "sad"
  | "angry"
  | "excited"
  | "calm"
  | "whisper";

export type VoiceEmotionChoice = VoiceEmotion | "auto";

export const VOICE_EMOTIONS: VoiceEmotion[] = [
  "neutral",
  "happy",
  "sad",
  "angry",
  "excited",
  "calm",
  "whisper",
];

export const VOICE_EMOTION_CHOICES: VoiceEmotionChoice[] = [
  "auto",
  ...VOICE_EMOTIONS,
];

export type VoiceSessionState = {
  status: VoiceSessionStatus;
  userId: string;
  profile: VoiceProfile | null;
  error: string | null;
};

let voiceSessionState: VoiceSessionState = {
  status: "loading",
  userId: "",
  profile: null,
  error: null,
};
let refreshPromise: Promise<VoiceSessionState> | null = null;
let refreshUserId: string | null = null;
let refreshSessionCtrl: AbortController | null = null;
const voiceListeners = new Set<(state: VoiceSessionState) => void>();

function linkAbortParent(controller: AbortController, parent?: AbortSignal): () => void {
  if (!parent) return () => {};
  if (parent.aborted) {
    controller.abort();
    return () => {};
  }
  const onAbort = () => controller.abort();
  parent.addEventListener("abort", onAbort, { once: true });
  return () => parent.removeEventListener("abort", onAbort);
}

export function isCloneMockMode(): boolean {
  return FORCE_MOCK || !API_URL;
}

export function getOrCreateVoiceId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = newUuid();
    setVoiceId(id);
  }
  return id;
}

export function getCurrentVoiceId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function clearVoiceId(): void {
  if (typeof window === "undefined") return;
  const previous = getCurrentVoiceId();
  window.localStorage.removeItem(STORAGE_KEY);
  if (previous) invalidateVoiceCaches(previous);
  publishVoiceSession(null, "");
}

export function rotateVoiceId(): string {
  const next = newUuid();
  setVoiceId(next);
  return next;
}

function setVoiceId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, id);
  window.dispatchEvent(new CustomEvent(VOICE_EVENT, { detail: getVoiceSessionSnapshot() }));
}

function newUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "u_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export type VoiceTake = {
  id: string;
  ref_text: string;
  duration_s: number;
  created_at: number;
};

export type VoiceProfile = {
  user_id: string;
  takes: VoiceTake[];
  ref_text: string;
  duration_s: number;
  bundle_duration_s: number;
  created_at: number;
  updated_at: number;
  revision: string;
};

export type EnrollmentPrompt = {
  id: string;
  label: string;
  text: string;
  hint?: string;
};

/**
 * Upstream CosyVoice zero-shot examples use a brief prompt audio clip with
 * its exact transcript. Keep the default enrollment short enough that users
 * can read it cleanly in one natural take; optional prompts stay available
 * when they choose to strengthen the profile.
 */
export const VOICE_PROFILE_PROMPTS: EnrollmentPrompt[] = [
  {
    id: "voice-card",
    label: "Voice sample",
    text:
      "Hi, this is my voice sample for PronounceAI. I speak clearly at a natural pace, with calm energy. " +
      "The weather today feels bright, fresh, and easy.",
    hint: "Read once, naturally, in a quiet room.",
  },
  {
    id: "question",
    label: "Question",
    text:
      "Could you show me the fastest route to the station? I will arrive at seven fifteen and call when I get there.",
    hint: "Use normal question intonation.",
  },
  {
    id: "contrast",
    label: "Contrast",
    text:
      "Yesterday I thought the little red light looked brighter than usual, but everything worked fine.",
    hint: "Keep it relaxed and conversational.",
  },
];

export const ENROLLMENT_PROMPTS: EnrollmentPrompt[] = [VOICE_PROFILE_PROMPTS[0]];

export const ENROLLMENT_PHRASE = VOICE_PROFILE_PROMPTS[0].text; // legacy export

export function chooseEnrollmentPrompts(profile?: VoiceProfile | null): EnrollmentPrompt[] {
  const used = new Set(profile?.takes?.map((take) => take.ref_text) ?? []);
  const next = VOICE_PROFILE_PROMPTS.find((prompt) => !used.has(prompt.text)) ?? VOICE_PROFILE_PROMPTS[0];
  return [next];
}

function profileRevision(profile: VoiceProfile): string {
  return String(profile.revision || profile.updated_at || profile.created_at || "legacy");
}

function rememberVoiceProfile(profile: VoiceProfile): void {
  const nextRevision = profileRevision(profile);
  const previousRevision = knownVoiceRevisions.get(profile.user_id);
  if (previousRevision !== nextRevision) invalidateVoiceCaches(profile.user_id);
  knownVoiceRevisions.set(profile.user_id, nextRevision);
}

export function invalidateVoiceCaches(userId?: string): void {
  if (!userId) {
    voiceClipCache.clear();
    return;
  }
  for (const key of Array.from(voiceClipCache.keys())) {
    if (key.startsWith(`${userId}:`)) voiceClipCache.delete(key);
  }
}

function emitVoiceSession(state: VoiceSessionState): VoiceSessionState {
  voiceSessionState = state;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(VOICE_EVENT, { detail: state }));
  }
  voiceListeners.forEach((listener) => listener(state));
  return state;
}

export function publishVoiceSession(
  profile: VoiceProfile | null,
  userId = profile?.user_id ?? getCurrentVoiceId() ?? "",
  error: string | null = null
): VoiceSessionState {
  if (profile) {
    rememberVoiceProfile(profile);
    return emitVoiceSession({
      status: "ready",
      userId: profile.user_id,
      profile,
      error,
    });
  }
  return emitVoiceSession({
    status: error ? "error" : "none",
    userId,
    profile: null,
    error,
  });
}

export function getVoiceSessionSnapshot(): VoiceSessionState {
  if (typeof window === "undefined") return voiceSessionState;
  const userId = getCurrentVoiceId() ?? voiceSessionState.userId;
  if (!userId || voiceSessionState.userId === userId) return { ...voiceSessionState, userId };
  return { status: "loading", userId, profile: null, error: null };
}

export function subscribeVoiceSession(cb: (state: VoiceSessionState) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (event: StorageEvent) => {
    if (!event.key || event.key === STORAGE_KEY) {
      refreshVoiceSession({ force: true }).catch(() => {});
    }
  };
  voiceListeners.add(cb);
  window.addEventListener("storage", onStorage);
  return () => {
    voiceListeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export async function refreshVoiceSession(
  opts: { force?: boolean; signal?: AbortSignal } = {}
): Promise<VoiceSessionState> {
  if (typeof window === "undefined") return voiceSessionState;
  const userId = getOrCreateVoiceId();
  const current = getVoiceSessionSnapshot();
  if (!opts.force && current.userId === userId && current.status !== "loading") {
    return current;
  }
  if (!opts.force && refreshPromise && refreshUserId === userId) {
    return refreshPromise;
  }

  refreshSessionCtrl?.abort();
  const ctrl = new AbortController();
  refreshSessionCtrl = ctrl;
  const unlinkParent = linkAbortParent(ctrl, opts.signal);

  if (!current.profile) {
    emitVoiceSession({ status: "loading", userId, profile: null, error: null });
  }

  refreshUserId = userId;

  const promise = fetchVoiceProfile(userId, { signal: ctrl.signal })
    .then((profile) => {
      if (getCurrentVoiceId() !== userId) return getVoiceSessionSnapshot();
      return publishVoiceSession(profile, userId);
    })
    .catch((error) => {
      if (isAbortError(error)) return getVoiceSessionSnapshot();
      if (getCurrentVoiceId() !== userId) return getVoiceSessionSnapshot();
      const message = (error as Error).message ?? "Could not check voice profile.";
      const latest = getVoiceSessionSnapshot();
      if (latest.userId === userId && latest.profile) {
        return emitVoiceSession({ ...latest, status: "ready", error: message });
      }
      return publishVoiceSession(null, userId, message);
    })
    .finally(() => {
      unlinkParent();
      if (refreshSessionCtrl === ctrl) refreshSessionCtrl = null;
      if (refreshPromise === promise) {
        refreshPromise = null;
        refreshUserId = null;
      }
    });

  refreshPromise = promise;
  return promise;
}

export async function fetchVoiceProfile(
  userId: string,
  opts?: { signal?: AbortSignal }
): Promise<VoiceProfile | null> {
  if (!userId || isCloneMockMode()) return null;
  const res = await fetch(`${API_URL}/api/voice/${encodeURIComponent(userId)}`, {
    signal: opts?.signal,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Fetch voice profile failed (${res.status})`);
  const profile = (await res.json()) as VoiceProfile;
  rememberVoiceProfile(profile);
  return profile;
}

/** Append a new take to the user's enrollment. Returns the updated profile. */
export async function addVoiceTake(
  userId: string,
  audioBlob: Blob,
  refText: string,
  opts?: { signal?: AbortSignal }
): Promise<VoiceProfile> {
  if (isCloneMockMode()) {
    throw new Error("Voice enrollment requires the live backend (mock mode is off).");
  }
  const form = new FormData();
  form.append("audio", audioBlob, "take.webm");
  form.append("ref_text", refText);
  form.append("user_id", userId);
  const res = await fetch(`${API_URL}/api/voice/enroll`, {
    method: "POST",
    body: form,
    signal: opts?.signal,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(msg || `Take upload failed (${res.status})`);
  }
  const profile = await fetchVoiceProfile(userId, { signal: opts?.signal });
  if (!profile) throw new Error("Take saved but profile fetch failed.");
  publishVoiceSession(profile);
  return profile;
}

/** Back-compat alias kept for callers that haven't migrated. */
export const enrollVoice = (userId: string, audio: Blob, refText: string) =>
  addVoiceTake(userId, audio, refText);

export async function deleteVoiceTake(
  userId: string,
  takeId: string,
  opts?: { signal?: AbortSignal }
): Promise<VoiceProfile | null> {
  if (!userId || isCloneMockMode()) return null;
  const res = await fetch(
    `${API_URL}/api/voice/${encodeURIComponent(userId)}/takes/${encodeURIComponent(takeId)}`,
    { method: "DELETE", signal: opts?.signal }
  );
  if (!res.ok) throw new Error(`Delete take failed (${res.status})`);
  invalidateVoiceCaches(userId);
  const profile = await fetchVoiceProfile(userId, { signal: opts?.signal });
  publishVoiceSession(profile, userId);
  return profile;
}

export async function deleteVoiceProfile(userId: string, opts?: { signal?: AbortSignal }): Promise<void> {
  if (!userId || isCloneMockMode()) return;
  const res = await fetch(`${API_URL}/api/voice/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    signal: opts?.signal,
  });
  if (!res.ok) throw new Error(`Delete voice profile failed (${res.status})`);
  invalidateVoiceCaches(userId);
  const nextId = getCurrentVoiceId() === userId ? rotateVoiceId() : getCurrentVoiceId() ?? "";
  publishVoiceSession(null, nextId);
}

export async function deleteCurrentVoiceProfile(opts?: { signal?: AbortSignal }): Promise<void> {
  const userId = getCurrentVoiceId();
  if (userId) {
    await deleteVoiceProfile(userId, opts);
    return;
  }
  publishVoiceSession(null, rotateVoiceId());
}

export type WordTiming = {
  word: string;
  start_ms: number;
  end_ms: number;
};

export type SpokenClip = {
  audio: Blob;
  words: WordTiming[];
  accent: "GA" | "RP";
  text: string;
  renderMode: VoiceRenderMode;
  emotion: VoiceEmotion;
  emotionSource: "auto" | "manual";
  detectedRawLabel?: string;
  detectedScore?: number;
  synthesisMode?: string;
};

function rememberVoiceClip(key: string, promise: Promise<SpokenClip>): Promise<SpokenClip> {
  if (voiceClipCache.has(key)) voiceClipCache.delete(key);
  voiceClipCache.set(key, promise);
  while (voiceClipCache.size > MAX_VOICE_CLIP_CACHE) {
    const oldest = voiceClipCache.keys().next().value as string;
    voiceClipCache.delete(oldest);
  }
  return promise;
}

function voiceClipKey(
  userId: string,
  text: string,
  accent: "GA" | "RP",
  revision?: string,
  renderMode: VoiceRenderMode = "target_accent",
  emotion: VoiceEmotionChoice = "neutral"
): string {
  const rev = revision ?? knownVoiceRevisions.get(userId) ?? "no-revision";
  return `${userId}:${rev}:${accent}:${renderMode}:${emotion}:${text.trim().slice(0, 400)}`;
}

function decodeWordTimings(header: string | null): WordTiming[] {
  if (!header) return [];
  try {
    const json = atob(header);
    const parsed = JSON.parse(json);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (w) => w && typeof w.word === "string" && typeof w.start_ms === "number"
    );
  } catch {
    return [];
  }
}

/**
 * Synthesise arbitrary text in the enrolled voice + target accent.
 * Default strategy is target-accent voice conversion: render the requested
 * accent first, then transfer it into the enrolled timbre. Natural mode keeps
 * zero-shot cloning available when the user wants the reference accent.
 */
export async function speakInVoice(
  userId: string,
  text: string,
  accent: "GA" | "RP",
  revision?: string,
  renderMode: VoiceRenderMode = "target_accent",
  signal?: AbortSignal,
  emotion: VoiceEmotionChoice = "neutral"
): Promise<SpokenClip> {
  if (isCloneMockMode()) {
    throw new Error("Voice synthesis requires the live backend (mock mode is off).");
  }
  return getVoiceClip(userId, text, accent, revision, renderMode, signal, emotion);
}

function getVoiceClip(
  userId: string,
  text: string,
  accent: "GA" | "RP",
  revision?: string,
  renderMode: VoiceRenderMode = "target_accent",
  signal?: AbortSignal,
  emotion: VoiceEmotionChoice = "neutral"
): Promise<SpokenClip> {
  const normalized = text.trim();
  const key = voiceClipKey(userId, normalized, accent, revision, renderMode, emotion);

  const execute = (): Promise<SpokenClip> =>
    fetch(`${API_URL}/api/voice/speak`, {
      method: "POST",
      body: buildSpeakForm(normalized, userId, accent, renderMode, emotion),
      signal,
    }).then(async (res) => {
      if (!res.ok) {
        const msg = await res.text().catch(() => res.statusText);
        throw new Error(`Voice synthesis failed: ${msg}`);
      }
      const audio = await res.blob();
      const words = decodeWordTimings(res.headers.get("X-Word-Timings"));
      const synthesisMode = res.headers.get("X-Voice-Mode") ?? undefined;
      const resolvedEmotion = (res.headers.get("X-Voice-Emotion") ?? "neutral") as VoiceEmotion;
      const emotionSource = (res.headers.get("X-Voice-Emotion-Source") ?? "manual") as "auto" | "manual";
      const detectedRawLabel = res.headers.get("X-Voice-Emotion-Raw") ?? undefined;
      const detectedScoreRaw = res.headers.get("X-Voice-Emotion-Score");
      const detectedScore = detectedScoreRaw != null ? Number(detectedScoreRaw) : undefined;
      return {
        audio,
        words,
        accent,
        text: normalized,
        renderMode,
        emotion: resolvedEmotion,
        emotionSource,
        detectedRawLabel,
        detectedScore,
        synthesisMode,
      };
    });

  /** Cancellable callers must not share LRU cache rows with aborted bodies. */
  if (signal) {
    return execute();
  }

  const cached = voiceClipCache.get(key);
  if (cached) return cached;

  const promise = execute().catch((error) => {
    voiceClipCache.delete(key);
    throw error;
  });
  return rememberVoiceClip(key, promise);
}

function buildSpeakForm(
  normalized: string,
  userId: string,
  accent: "GA" | "RP",
  renderMode: VoiceRenderMode,
  emotion: VoiceEmotionChoice = "neutral"
): FormData {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("text", normalized);
  form.append("accent", accent);
  form.append("strategy", renderMode);
  form.append("emotion", emotion);
  return form;
}

export function precomposeVoice(
  userId: string,
  text: string,
  accent: "GA" | "RP",
  revision?: string,
  renderMode: VoiceRenderMode = "target_accent",
  emotion: VoiceEmotionChoice = "neutral"
): void {
  if (isCloneMockMode() || !userId || text.trim().length < 2) return;
  getVoiceClip(userId, text, accent, revision, renderMode, undefined, emotion).catch(() => {
    // Speculative work is best-effort. The explicit click path will show errors.
  });
}

/** Personal accent clone from an input recording — preserves user's voice timbre. */
export async function cloneAccent(
  audioBlob: Blob,
  accent: "GA" | "RP",
  userId: string,
  opts?: { overrideText?: string; signal?: AbortSignal; emotion?: VoiceEmotionChoice }
): Promise<Blob> {
  if (isCloneMockMode()) {
    throw new Error("Accent clone requires the live backend (mock mode is off).");
  }
  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  form.append("accent", accent);
  form.append("user_id", userId);
  const overrideText = opts?.overrideText;
  if (overrideText) form.append("override_text", overrideText);
  if (opts?.emotion) form.append("emotion", opts.emotion);
  const res = await fetch(`${API_URL}/api/accent-clone`, {
    method: "POST",
    body: form,
    signal: opts?.signal,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Accent clone failed: ${msg}`);
  }
  return res.blob();
}
