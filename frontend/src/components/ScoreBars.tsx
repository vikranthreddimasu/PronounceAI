"use client";

import type { Scores } from "@/lib/types";

type Props = { scores: Scores; overall: number };

const DIMS: { key: keyof Scores; label: string; delay: number }[] = [
  { key: "phoneme_accuracy", label: "Phoneme accuracy", delay: 0   },
  { key: "intonation",       label: "Intonation",        delay: 60  },
  { key: "stress_rhythm",    label: "Stress & rhythm",   delay: 120 },
  { key: "vowel_quality",    label: "Vowel quality",     delay: 180 },
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

      {DIMS.map(({ key, label, delay }) => {
        const v = scores[key];
        const t = tone(v);
        return (
          <div key={key} className="flex items-center gap-3">
            <span style={{ fontSize: 12, color: "var(--ink-3)", width: 130, flexShrink: 0, fontWeight: 500 }}>
              {label}
            </span>

            <div className="dim-track" style={{ flex: 1, height: 6 }}>
              <div
                className="dim-fill"
                style={{ "--pct": `${v}%`, "--tone": t, "--delay": `${delay}ms` } as React.CSSProperties}
              />
            </div>

            <span style={{ fontSize: 12, color: t, fontWeight: 700, width: 36, textAlign: "right", fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
              {v}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
