"use client";

import type { Scores } from "@/lib/types";
import { useCountUp } from "@/lib/useCountUp";

type Props = { scores: Scores; overall: number };

const DIMS: { key: keyof Scores; label: string; note: string; delay: number }[] = [
  { key: "phoneme_accuracy", label: "Phonemes", note: "GOP alignment", delay: 0 },
  { key: "intonation", label: "Intonation", note: "F0 contour", delay: 60 },
  { key: "stress_rhythm", label: "Rhythm", note: "stress timing", delay: 120 },
  { key: "vowel_quality", label: "Vowels", note: "formant space", delay: 180 },
];

function tone(value: number) {
  return value >= 80 ? "var(--jade)" : value >= 60 ? "var(--ink)" : "var(--accent)";
}

export default function ScoreBars({ scores }: Props) {
  return (
    <div
      className="result-enter"
      style={{
        display: "grid",
        gap: 0,
        borderTop: "1px solid var(--ink)",
      }}
    >
      <p
        className="eyebrow"
        style={{ padding: "12px 0 10px", borderBottom: "1px solid var(--rule)" }}
      >
        Score Anatomy
      </p>
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
  const animated = useCountUp(value, 620, delay);
  const color = tone(value);

  return (
    <div
      style={{
        display: "grid",
        gap: 8,
        padding: "12px 0 14px",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      <div
        className="flex items-baseline justify-between"
        style={{ gap: 12 }}
      >
        <div style={{ minWidth: 0 }}>
          <p
            style={{
              color: "var(--ink)",
              fontFamily: "var(--type-sans)",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
            }}
          >
            {label}
          </p>
          <p
            className="font-mono"
            style={{
              color: "var(--ink-4)",
              fontSize: 10,
              letterSpacing: "0.04em",
              marginTop: 4,
              textTransform: "uppercase",
            }}
          >
            {note}
          </p>
        </div>
        <p
          className="font-mono"
          style={{
            color,
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Math.round(animated)}
        </p>
      </div>
      <div className="dim-track" style={{ height: 3 }}>
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
