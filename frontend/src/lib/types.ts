export type Accent = "GA" | "RP";

export type PhonemeResult = {
  phoneme: string;
  expected: string;
  gop: number;
  correct: boolean;
  substitution?: string;
  start_ms: number;
  end_ms: number;
};

export type Scores = {
  phoneme_accuracy: number;  // 0–100
  intonation: number;
  stress_rhythm: number;
  vowel_quality: number;
};

export type FeedbackTip = {
  text: string;
  timestamp_ms?: number;
};

/**
 * Pitch contour — F0 over time, z-score normalised within voiced frames.
 * Same length for native + user so they overlay on a shared x-axis.
 * Unvoiced frames are `null` (so the line breaks naturally).
 */
export type PitchContour = {
  native: (number | null)[];
  user: (number | null)[];
  duration_ms: number;  // total span the contour represents
};

export type AssessmentResult = {
  phonemes: PhonemeResult[];
  scores: Scores;
  feedback: FeedbackTip[];   // deprecated — kept for backwards compat; not rendered
  overall: number;
  pitch_contour?: PitchContour;
};

export type Phrase = {
  id: string;
  text: string;
  focus: string;         // e.g. "th-sounds", "connected-speech"
  category: "minimal-pair" | "phoneme-drill" | "connected-speech" | "authentic";
};

export type AppState =
  | { phase: "idle" }
  | { phase: "recording" }
  | { phase: "processing" }
  | { phase: "result"; result: AssessmentResult };
