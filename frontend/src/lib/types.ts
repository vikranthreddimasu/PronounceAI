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

export type AssessmentResult = {
  phonemes: PhonemeResult[];
  scores: Scores;
  feedback: FeedbackTip[];
  overall: number;
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
