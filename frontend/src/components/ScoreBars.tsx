"use client";

import type { Scores } from "@/lib/types";
import { useCountUp } from "@/lib/useCountUp";

type Props = { scores: Scores; overall: number };

const DIMS: { key: keyof Scores; label: string; note: string; delay: number }[] = [
  { key: "phoneme_accuracy", label: "Phonemes", note: "GOP alignment", delay: 0 },
  { key: "intonation", label: "Intonation", note: "F0 contour", delay: 90 },
  { key: "stress_rhythm", label: "Rhythm", note: "stress timing", delay: 180 },
  { key: "vowel_quality", label: "Vowels", note: "formant space", delay: 270 },
];

function tone(value: number) {
  return value >= 80 ? "var(--jade)" : value >= 60 ? "var(--accent)" : "var(--rose)";
}

export default function ScoreBars({ scores }: Props) {
  return (
    <div className="result-enter" style={{ display: "grid", gap: 12 }}>
      <p className="eyebrow">Score anatomy</p>
      {DIMS.map(({ key, label, note, delay }) => (
        <DimRow key={key} label={label} note={note} value={scores[key]} delay={delay} />
      ))}
    </div>
  );
}

function DimRow({
  label,
  note,
  value,
  delay,
}: {
  label: string;
  note: string;
  value: number;
  delay: number;
}) {
  const animated = useCountUp(value, 900, delay);
  const color = tone(value);

  return (
    <div className="quiet-panel" style={{ padding: "12px 12px 11px" }}>
      <div className="flex items-end justify-between" style={{ gap: 12, marginBottom: 9 }}>
        <div style={{ minWidth: 0 }}>
          <p style={{ color: "var(--ink)", fontSize: 13, fontWeight: 640, letterSpacing: 0 }}>
            {label}
          </p>
          <p className="font-mono" style={{ color: "var(--ink-4)", fontSize: 10, letterSpacing: 0, marginTop: 2 }}>
            {note}
          </p>
        </div>
        <p className="font-mono" style={{ color, fontSize: 13, fontWeight: 650 }}>
          {Math.round(animated)}%
        </p>
      </div>
      <div className="dim-track" style={{ height: 6 }}>
        <div
          className="dim-fill"
          style={{
            "--pct": `${animated}%`,
            "--tone": color,
          } as React.CSSProperties}
        />
      </div>
    </div>
  );
}
