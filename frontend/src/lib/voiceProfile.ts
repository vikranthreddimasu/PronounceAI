"use client";

/**
 * Voice profile = multi-take enrollment store, persisted server-side as
 * `data/enrollments/<userId>/take_NNN.wav` and bundled into a single 24kHz
 * reference clip (≤28s) that CosyVoice 3 ingests directly.
 *
 * The browser holds only an opaque UUID handle in localStorage so the
 * backend can look up the user's takes. No accounts, no PII.
 */

const STORAGE_KEY = "pronounceai.voice_id";
const API_URL = process.env.NEXT_PUBLIC_API_URL;
const FORCE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

export function isCloneMockMode(): boolean {
  return FORCE_MOCK || !API_URL;
}

export function getOrCreateVoiceId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = newUuid();
    window.localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function clearVoiceId(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
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
};

export type EnrollmentPrompt = {
  id: string;
  label: string;
  text: string;
  hint?: string;
};

/**
 * Three short, phoneme-balanced + prosody-varied passages.
 * Reading all three gives CosyVoice ~30s of clean reference covering wide
 * F0 range, every English consonant, plus questions and emphatic stress.
 */
export const ENROLLMENT_PROMPTS: EnrollmentPrompt[] = [
  {
    id: "phoneme",
    label: "Pangram",
    text:
      "Hello, my name is Alex. The quick brown fox jumps over the lazy dog by the river. " +
      "She sells seashells by the seashore, while three thoughtful theorists thought through thorny problems.",
    hint: "Steady, conversational pace.",
  },
  {
    id: "prosody",
    label: "Expressive",
    text:
      "Did you really think that would work? Honestly, I cannot believe it! " +
      "Sometimes the simplest answer is right there in front of us, hiding in plain sight.",
    hint: "Let the questions rise and the exclamation pop.",
  },
  {
    id: "numbers",
    label: "Numbers & names",
    text:
      "The flight departs at five forty-two in the morning, arriving at three eighteen. " +
      "Please confirm gate B twelve before boarding. The current temperature is fifty-seven degrees Fahrenheit.",
    hint: "Read it like you're announcing it.",
  },
];

export const ENROLLMENT_PHRASE = ENROLLMENT_PROMPTS[0].text; // legacy export

export async function fetchVoiceProfile(userId: string): Promise<VoiceProfile | null> {
  if (!userId || isCloneMockMode()) return null;
  const res = await fetch(`${API_URL}/api/voice/${encodeURIComponent(userId)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Fetch voice profile failed (${res.status})`);
  return res.json();
}

/** Append a new take to the user's enrollment. Returns the updated profile. */
export async function addVoiceTake(
  userId: string,
  audioBlob: Blob,
  refText: string
): Promise<VoiceProfile> {
  if (isCloneMockMode()) {
    throw new Error("Voice enrollment requires the live backend (mock mode is off).");
  }
  const form = new FormData();
  form.append("audio", audioBlob, "take.webm");
  form.append("ref_text", refText);
  form.append("user_id", userId);
  const res = await fetch(`${API_URL}/api/voice/enroll`, { method: "POST", body: form });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(msg || `Take upload failed (${res.status})`);
  }
  const profile = await fetchVoiceProfile(userId);
  if (!profile) throw new Error("Take saved but profile fetch failed.");
  return profile;
}

/** Back-compat alias kept for callers that haven't migrated. */
export const enrollVoice = (userId: string, audio: Blob, refText: string) =>
  addVoiceTake(userId, audio, refText);

export async function deleteVoiceTake(userId: string, takeId: string): Promise<VoiceProfile | null> {
  if (!userId || isCloneMockMode()) return null;
  const res = await fetch(
    `${API_URL}/api/voice/${encodeURIComponent(userId)}/takes/${encodeURIComponent(takeId)}`,
    { method: "DELETE" }
  );
  if (!res.ok) throw new Error(`Delete take failed (${res.status})`);
  return fetchVoiceProfile(userId);
}

export async function deleteVoiceProfile(userId: string): Promise<void> {
  if (!userId || isCloneMockMode()) return;
  await fetch(`${API_URL}/api/voice/${encodeURIComponent(userId)}`, { method: "DELETE" });
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
};

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
 * Backend races instruct-mode (best accent) against Whisper validation,
 * falls back to VC if instruct drifts. Returns audio + word timings so the
 * client can highlight the current word during playback.
 */
export async function speakInVoice(
  userId: string,
  text: string,
  accent: "GA" | "RP"
): Promise<SpokenClip> {
  if (isCloneMockMode()) {
    throw new Error("Voice synthesis requires the live backend (mock mode is off).");
  }
  const form = new FormData();
  form.append("user_id", userId);
  form.append("text", text);
  form.append("accent", accent);
  const res = await fetch(`${API_URL}/api/voice/speak`, { method: "POST", body: form });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Voice synthesis failed: ${msg}`);
  }
  const audio = await res.blob();
  const words = decodeWordTimings(res.headers.get("X-Word-Timings"));
  return { audio, words, accent, text };
}

/** Personal accent clone from an input recording — preserves user's voice timbre. */
export async function cloneAccent(
  audioBlob: Blob,
  accent: "GA" | "RP",
  userId: string,
  overrideText?: string
): Promise<Blob> {
  if (isCloneMockMode()) {
    throw new Error("Accent clone requires the live backend (mock mode is off).");
  }
  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  form.append("accent", accent);
  form.append("user_id", userId);
  if (overrideText) form.append("override_text", overrideText);
  const res = await fetch(`${API_URL}/api/accent-clone`, { method: "POST", body: form });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Accent clone failed: ${msg}`);
  }
  return res.blob();
}
