import ScoreBars from "@/components/ScoreBars";
import FeedbackPanel from "@/components/FeedbackPanel";
import PhonemeTimeline from "@/components/PhonemeTimeline";
import type { AssessmentResult } from "@/lib/types";

const R: AssessmentResult = {
  overall: 76,
  scores: { phoneme_accuracy: 82, intonation: 68, stress_rhythm: 79, vowel_quality: 64 },
  phonemes: [
    { phoneme: "ð", expected: "ð", gop: -0.3, correct: true, start_ms: 120, end_ms: 180 },
    { phoneme: "ə", expected: "ə", gop: -0.2, correct: true, start_ms: 180, end_ms: 220 },
    { phoneme: "k", expected: "k", gop: -0.5, correct: true, start_ms: 220, end_ms: 280 },
    { phoneme: "w", expected: "w", gop: -0.7, correct: true, start_ms: 280, end_ms: 330 },
    { phoneme: "ɪ", expected: "ɪ", gop: -1.5, correct: false, start_ms: 330, end_ms: 380 },
    { phoneme: "k", expected: "k", gop: -0.4, correct: true, start_ms: 380, end_ms: 440 },
    { phoneme: "b", expected: "b", gop: -0.6, correct: true, start_ms: 480, end_ms: 540 },
    { phoneme: "r", expected: "r", gop: -1.8, correct: false, start_ms: 540, end_ms: 600 },
    { phoneme: "aʊ", expected: "aʊ", gop: -0.9, correct: true, start_ms: 600, end_ms: 700 },
    { phoneme: "n", expected: "n", gop: -0.3, correct: true, start_ms: 700, end_ms: 750 },
    { phoneme: "f", expected: "f", gop: -2.4, correct: false, substitution: "b→f", start_ms: 800, end_ms: 870 },
    { phoneme: "ɒ", expected: "ɒ", gop: -0.5, correct: true, start_ms: 870, end_ms: 930 },
  ],
  feedback: [
    { text: "Your /f/ in 'fox' is too close to /b/ — press the upper teeth against the lower lip and keep air flowing continuously; there should be no full stop.", timestamp_ms: 800 },
    { text: "Your /ɪ/ (as in 'quick') is drifting toward /iː/. Keep the tongue lower and slightly back — it's a lax vowel, not the tense /iː/ in 'sheep'.", timestamp_ms: 330 },
    { text: "Your intonation falls too early. In GA, sustain the pitch through 'brown fox' before the final drop on 'dog'." },
  ],
};

function verdictLabel(s: number) {
  if (s >= 90) return "Native-level";
  if (s >= 80) return "Strong";
  if (s >= 70) return "Getting there";
  if (s >= 55) return "Building";
  return "Keep going";
}

export default function Dev() {
  const color = R.overall >= 80 ? "var(--jade)" : R.overall >= 65 ? "var(--accent)" : "var(--rose)";
  return (
    <main style={{ maxWidth: 440, margin: "0 auto", padding: "40px 20px", display: "flex", flexDirection: "column", gap: 28 }}>
      <p className="font-display" style={{ fontSize: 26, fontWeight: 700, color: "var(--ink)" }}>The quick brown fox</p>
      <div className="result-enter flex items-center" style={{ gap: 20 }}>
        <div className="flex flex-col items-center justify-center rounded-2xl" style={{ width: 72, height: 72, flexShrink: 0, background: color + "15", border: `2px solid ${color}` }}>
          <span style={{ fontSize: 26, fontWeight: 800, color, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{R.overall}</span>
          <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.06em", color, textTransform: "uppercase" as const, opacity: 0.8, marginTop: 3 }}>/ 100</span>
        </div>
        <div>
          <p style={{ fontSize: 20, fontWeight: 700, color: "var(--ink)", lineHeight: 1.1, marginBottom: 4 }}>{verdictLabel(R.overall)}</p>
          <p style={{ fontSize: 12, color: "var(--ink-4)" }}>See below for what to fix.</p>
        </div>
      </div>
      <PhonemeTimeline phonemes={R.phonemes} />
      <ScoreBars scores={R.scores} overall={R.overall} />
      <FeedbackPanel tips={R.feedback} />
    </main>
  );
}
