"use client";

import type { Scores } from "@/lib/types";
import { useCountUp } from "@/lib/useCountUp";

type Props = { scores: Scores; overall: number };

const DIMS: { key: keyof Scores; label: string; delay: number }[] = [
  { key: "phoneme_accuracy", label: "Phoneme accuracy", delay: 0 },
  { key: "intonation", label: "Intonation", delay: 90 },
  { key: "stress_rhythm", label: "Stress & rhythm", delay: 180 },
  { key: "vowel_quality", label: "Vowel quality", delay: 270 },
];

function tone(v: number) {
  return v >= 80 ? "var(--jade)" : v >= 60 ? "var(--accent)" : "var(--rose)";
}

export default function ScoreBars({ scores }: Props) {
  return (
    <div className="result-enter flex flex-col" style={{ gap: 12 }}>
      <p
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--ink-4)",
          marginBottom: 4,
        }}
      >
        Breakdown
      </p>

      {DIMS.map(({ key, label, delay }) => (
        <DimRow key={key} label={label} value={scores[key]} delay={delay} />
      ))}
    </div>
  );
}

function DimRow({
  label,
  value,
  delay,
}: {
  label: string;
  value: number;
  delay: number;
}) {
  const animated = useCountUp(value, 900, delay);
  const t = tone(value);

  return (
    <div className="flex items-center gap-3">
      <span
        style={{
          fontSize: 12,
          color: "var(--ink-3)",
          width: 130,
          flexShrink: 0,
          fontWeight: 500,
        }}
      >
        {label}
      </span>

      <div
        style={{
          flex: 1,
          height: 6,
          borderRadius: 3,
          background: "var(--surface-2)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            width: `${animated}%`,
            background: `linear-gradient(90deg, ${t}99, ${t})`,
            borderRadius: 3,
          }}
        />
        {/* Soft shimmer at the leading edge */}
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: `calc(${animated}% - 12px)`,
            width: 12,
            background: `linear-gradient(90deg, transparent, ${t}66)`,
            borderRadius: 3,
            opacity: animated < value ? 1 : 0,
            transition: "opacity 220ms var(--ease-out)",
          }}
        />
      </div>

      <span
        style={{
          fontSize: 12,
          color: t,
          fontWeight: 700,
          width: 36,
          textAlign: "right",
          fontVariantNumeric: "tabular-nums",
          flexShrink: 0,
        }}
      >
        {Math.round(animated)}%
      </span>
    </div>
  );
}
