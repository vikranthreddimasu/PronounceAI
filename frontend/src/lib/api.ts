import type { AssessmentResult } from "./types";
import { generateMockResult } from "./mock";
import { speakReference } from "./recorder";

const API_URL = process.env.NEXT_PUBLIC_API_URL;
const FORCE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

export function isMockMode(): boolean {
  return FORCE_MOCK || !API_URL;
}

export async function scoreRecording(
  audioBlob: Blob,
  phraseText: string,
  accent: "GA" | "RP" = "GA",
  l1: string = "unknown"
): Promise<AssessmentResult> {
  if (isMockMode()) {
    await new Promise((r) => setTimeout(r, 900 + Math.random() * 600));
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
  speed: number = 0.9
): Promise<void> {
  if (isMockMode()) {
    return speakReference(text);
  }

  const url = `${API_URL}/api/tts?text=${encodeURIComponent(text)}&accent=${accent}&speed=${speed}`;
  const res = await fetch(url);
  if (!res.ok) {
    // Graceful fallback to browser TTS if Kokoro fails
    return speakReference(text);
  }

  const blob = await res.blob();
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);

  return new Promise((resolve) => {
    audio.onended = () => { URL.revokeObjectURL(audioUrl); resolve(); };
    audio.onerror = () => { URL.revokeObjectURL(audioUrl); resolve(); };
    audio.play().catch(() => { URL.revokeObjectURL(audioUrl); resolve(); });
  });
}

/**
 * Convert the user's recording into the target accent using kNN-VC on the backend.
 * Returns a Blob (audio/wav). Caller is responsible for object-URL lifecycle.
 * In mock mode this throws so the UI can show a "live only" hint.
 */
export async function convertAccent(
  audioBlob: Blob,
  accent: "GA" | "RP"
): Promise<Blob> {
  if (isMockMode()) {
    throw new Error("Accent conversion requires the live backend (mock mode is off).");
  }

  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  form.append("accent", accent);

  const res = await fetch(`${API_URL}/api/accent-convert`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`Accent conversion failed: ${msg}`);
  }
  return res.blob();
}
