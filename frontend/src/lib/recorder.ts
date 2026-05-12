/**
 * Thin wrapper around MediaRecorder + a real-time audio level analyser.
 *
 * The level (0..1) is exposed via `subscribeLevel()` so the UI can drive
 * a ring/meter that physically responds to the user's voice — not a
 * generic CSS pulse. This is the "feels alive" detail.
 */
export type Recorder = {
  start: () => Promise<void>;
  stop: () => Promise<Blob>;
  /** Call from rAF loop. Returns 0..1 RMS level (decayed) or null when idle. */
  getLevel: () => number | null;
  dispose: () => void;
};

const PREFERRED_MIME_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const t of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return undefined;
}

export async function createRecorder(): Promise<Recorder> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone access is not available in this browser.");
  }

  let stream: MediaStream | null = null;
  let recorder: MediaRecorder | null = null;
  let audioCtx: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let timeData: Uint8Array | null = null;
  let lastLevel = 0;
  let active = false;

  let chunks: Blob[] = [];
  const mimeType = pickMimeType();

  async function ensureStream() {
    if (stream) return stream;
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    return stream;
  }

  function ensureAnalyser(s: MediaStream) {
    if (analyser) return;
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    audioCtx = new Ctx();
    source = audioCtx.createMediaStreamSource(s);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.6;
    source.connect(analyser);
    timeData = new Uint8Array(analyser.fftSize);
  }

  return {
    async start() {
      const s = await ensureStream();
      ensureAnalyser(s);
      if (audioCtx?.state === "suspended") await audioCtx.resume();
      chunks = [];
      recorder = new MediaRecorder(s, mimeType ? { mimeType } : undefined);
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };
      recorder.start();
      active = true;
    },
    stop() {
      return new Promise<Blob>((resolve, reject) => {
        if (!recorder) {
          reject(new Error("recorder not started"));
          return;
        }
        if (recorder.state === "inactive") {
          // Already stopped — return whatever chunks we have rather than hanging.
          const type = mimeType ?? "audio/webm";
          resolve(new Blob(chunks, { type }));
          return;
        }
        recorder.onstop = () => {
          active = false;
          const type = mimeType ?? "audio/webm";
          resolve(new Blob(chunks, { type }));
        };
        recorder.onerror = (e) => reject(new Error((e as Event).type ?? "recorder error"));
        try {
          recorder.stop();
        } catch (e) {
          reject(e);
        }
      });
    },
    getLevel() {
      if (!active || !analyser || !timeData) return null;
      // getByteTimeDomainData expects Uint8Array<ArrayBuffer>; cast is safe
      // because we created timeData from a normal ArrayBuffer above.
      analyser.getByteTimeDomainData(timeData as Uint8Array<ArrayBuffer>);
      // RMS over the time-domain buffer, normalised around 128 (silence).
      let sum = 0;
      for (let i = 0; i < timeData.length; i++) {
        const v = (timeData[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / timeData.length);
      // Stretch quiet speech (~0.05 rms) up to ~0.8 of the meter.
      const scaled = Math.min(1, Math.pow(rms * 4.5, 0.85));
      // Smooth attack/release: fast attack, slow release.
      lastLevel =
        scaled > lastLevel
          ? lastLevel + (scaled - lastLevel) * 0.5
          : lastLevel + (scaled - lastLevel) * 0.12;
      return lastLevel;
    },
    dispose() {
      active = false;
      try {
        source?.disconnect();
      } catch {}
      try {
        analyser?.disconnect();
      } catch {}
      audioCtx?.close().catch(() => {});
      stream?.getTracks().forEach((t) => t.stop());
      stream = null;
      recorder = null;
      analyser = null;
      source = null;
      audioCtx = null;
      timeData = null;
      chunks = [];
    },
  };
}

export type SpeakReferenceOptions = {
  signal?: AbortSignal;
};

/** Speak text with the browser's TTS as a mock-mode native reference. */
export function speakReference(text: string, opts?: SpeakReferenceOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    const signal = opts?.signal;
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      resolve();
      return;
    }
    let settled = false;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    u.rate = 0.95;
    u.pitch = 1.0;

    const detachAbort = () => signal?.removeEventListener("abort", onAbort);

    const onAbort = () => {
      detachAbort();
      window.speechSynthesis.cancel();
      if (settled) return;
      settled = true;
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    u.onend = () => {
      if (settled) return;
      settled = true;
      detachAbort();
      resolve();
    };
    u.onerror = () => {
      if (settled) return;
      settled = true;
      detachAbort();
      resolve();
    };
    window.speechSynthesis.speak(u);
  });
}
