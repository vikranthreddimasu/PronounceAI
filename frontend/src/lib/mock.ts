import type { AssessmentResult, PhonemeResult, PitchContour, Scores } from "./types";

// CMU-style ARPAbet phonemes for common words
const PHONEME_MAP: Record<string, string[]> = {
  "the": ["ð", "ə"],
  "quick": ["k", "w", "ɪ", "k"],
  "brown": ["b", "r", "aʊ", "n"],
  "fox": ["f", "ɒ", "k", "s"],
  "jumps": ["dʒ", "ʌ", "m", "p", "s"],
  "over": ["oʊ", "v", "ə", "r"],
  "lazy": ["l", "eɪ", "z", "i"],
  "dog": ["d", "ɒ", "g"],
  "ship": ["ʃ", "ɪ", "p"],
  "sheep": ["ʃ", "iː", "p"],
  "this": ["ð", "ɪ", "s"],
  "thin": ["θ", "ɪ", "n"],
  "thing": ["θ", "ɪ", "ŋ"],
  "three": ["θ", "r", "iː"],
  "free": ["f", "r", "iː"],
};

function gaussianRandom(mean: number, std: number): number {
  // Box-Muller
  const u = 1 - Math.random();
  const v = Math.random();
  const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  return Math.max(0, Math.min(100, Math.round(mean + z * std)));
}

function mockScores(): Scores {
  return {
    phoneme_accuracy: gaussianRandom(72, 12),
    intonation: gaussianRandom(68, 14),
    stress_rhythm: gaussianRandom(75, 10),
    vowel_quality: gaussianRandom(65, 15),
  };
}

function gopFromAccuracy(isCorrect: boolean): number {
  if (isCorrect) return -(Math.random() * 0.8);          // 0 to -0.8 → green
  if (Math.random() < 0.4) return -(1 + Math.random());  // -1 to -2 → yellow
  return -(2 + Math.random() * 1.5);                      // -2 to -3.5 → red
}

function tokenise(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z\s]/g, "")
    .split(/\s+/)
    .filter(Boolean);
}

function buildPhonemes(text: string): PhonemeResult[] {
  const words = tokenise(text);
  const phonemes: PhonemeResult[] = [];
  let cursor = 120;

  for (const word of words) {
    const phones = PHONEME_MAP[word] ?? word.split("").slice(0, 4).map(() => "ə");
    for (const ph of phones) {
      const dur = 60 + Math.floor(Math.random() * 100);
      const correct = Math.random() > 0.22;
      const gop = gopFromAccuracy(correct);
      const sub = !correct && Math.random() > 0.5
        ? pickSubstitution(ph)
        : undefined;
      phonemes.push({
        phoneme: sub ?? ph,
        expected: ph,
        gop,
        correct,
        substitution: sub ? `${sub}→${ph}` : undefined,
        start_ms: cursor,
        end_ms: cursor + dur,
      });
      cursor += dur + 10;
    }
    cursor += 40; // inter-word gap
  }
  return phonemes;
}

const COMMON_SUBS: Record<string, string> = {
  "θ": "d", "ð": "d", "r": "l", "l": "r",
  "v": "b", "w": "v", "z": "s", "ʃ": "s",
  "dʒ": "j", "æ": "e", "ɪ": "i",
};
function pickSubstitution(ph: string): string {
  return COMMON_SUBS[ph] ?? ph.slice(-1);
}

const FEEDBACK_BANK: string[] = [
  "Your /θ/ sounds like /d/ — press the tongue tip lightly between your upper and lower front teeth and push air through.",
  "Your /r/ is too close to /l/. Curl the tongue back slightly without touching the palate; the /r/ is a non-contact sound in GA.",
  "Your rhythm is syllable-timed: every syllable gets equal weight. In GA, unstressed syllables collapse to schwa — 'a' → /ə/, 'and' → /ən/.",
  "Your intonation falls too early in the phrase. Keep the pitch level through the middle of the sentence before the final drop.",
  "Your /æ/ (as in 'bad') is too close to /e/. Drop the jaw lower and spread the lips wider — it should feel exaggerated.",
  "Your /v/ sounds like /b/. The upper teeth should lightly touch the lower lip while air keeps flowing — no full stop.",
  "The vowel in 'NURSE' words (work, world, word) needs more lip rounding and a central tongue body — avoid /ɛ/ or /ɔ/.",
  "Your /ʃ/ (as in 'she') is getting close to /s/. Round your lips slightly and push the tongue body back from the teeth.",
];

function pickFeedback(phonemes: PhonemeResult[]): Array<{ text: string; timestamp_ms?: number }> {
  const errors = phonemes.filter((p) => !p.correct);
  const tips: Array<{ text: string; timestamp_ms?: number }> = [];

  // Pick up to 3 unique tips
  const indices = new Set<number>();
  for (const err of errors.slice(0, 6)) {
    const idx = FEEDBACK_BANK.findIndex((t) =>
      t.includes(`/${err.expected}/`) && !indices.has(FEEDBACK_BANK.indexOf(t))
    );
    if (idx >= 0 && tips.length < 3) {
      indices.add(idx);
      tips.push({ text: FEEDBACK_BANK[idx], timestamp_ms: err.start_ms });
    }
  }

  // Fill remaining with random tips
  while (tips.length < Math.min(3, errors.length > 0 ? 3 : 1)) {
    const idx = Math.floor(Math.random() * FEEDBACK_BANK.length);
    if (!indices.has(idx)) {
      indices.add(idx);
      tips.push({ text: FEEDBACK_BANK[idx] });
    }
  }

  return tips.slice(0, 3);
}

/**
 * Build a plausible pitch contour pair for the result view.
 * Native: smooth declination + one accent peak per ~3 syllables.
 * User:   native + low-freq drift + occasional offset blocks + jitter.
 * Returns z-scored values; unvoiced frames are null so the line breaks.
 */
function mockPitchContour(phonemes: PhonemeResult[]): PitchContour {
  const last = phonemes[phonemes.length - 1];
  const duration_ms = (last?.end_ms ?? 1500) + 120;
  const N = 80;
  const native: (number | null)[] = new Array(N);
  const user: (number | null)[] = new Array(N);

  // Phrase-level declination (high → low over the utterance), plus 2–3 accent humps.
  const accentCount = 2 + Math.floor(Math.random() * 2);
  const accentCenters = Array.from({ length: accentCount }, (_, i) =>
    (i + 0.7) / accentCount + (Math.random() - 0.5) * 0.08
  );

  // User drift — slow random walk biased by user's intonation skill (mock).
  const driftAmp = 0.4 + Math.random() * 0.5;
  const driftFreq = 1.2 + Math.random() * 1.2;
  const driftPhase = Math.random() * Math.PI * 2;

  // Random "offset zone" — user goes flat or wrong direction in one segment.
  const flatStart = 0.25 + Math.random() * 0.35;
  const flatLen = 0.12 + Math.random() * 0.15;
  const flatBias = (Math.random() - 0.5) * 1.6;

  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);

    // Native shape
    const declination = 1.0 - t * 1.6;
    let accent = 0;
    for (const c of accentCenters) {
      const d = (t - c) / 0.08;
      accent += Math.exp(-d * d) * 0.9;
    }
    const nz = declination + accent;

    // User: drift + flat zone + small jitter
    const drift = Math.sin(t * Math.PI * 2 * driftFreq + driftPhase) * driftAmp;
    const inFlat = t > flatStart && t < flatStart + flatLen;
    const flat = inFlat ? flatBias * (1 - Math.abs((t - flatStart - flatLen / 2) / (flatLen / 2))) : 0;
    const jitter = (Math.random() - 0.5) * 0.18;
    const uz = nz + drift * 0.55 + flat + jitter;

    // Voicing gates — drop ~12% of frames as unvoiced (silence/consonants).
    native[i] = Math.random() < 0.1 ? null : Number(nz.toFixed(3));
    user[i] = Math.random() < 0.14 ? null : Number(uz.toFixed(3));
  }

  return { native, user, duration_ms };
}

export function generateMockResult(phraseText: string): AssessmentResult {
  const scores = mockScores();
  const phonemes = buildPhonemes(phraseText);
  const feedback = pickFeedback(phonemes);
  const pitch_contour = mockPitchContour(phonemes);
  const overall = Math.round(
    scores.phoneme_accuracy * 0.35 +
    scores.intonation * 0.20 +
    scores.stress_rhythm * 0.15 +
    scores.vowel_quality * 0.30
  );
  return { phonemes, scores, feedback, overall, pitch_contour };
}
