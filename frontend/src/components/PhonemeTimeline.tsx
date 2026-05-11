"use client";

import type { PhonemeResult } from "@/lib/types";

type Props = { phonemes: PhonemeResult[] };

function gopColor(gop: number): string {
  if (gop > -1.0) return "var(--jade)";
  if (gop > -2.0) return "var(--accent)";
  return "var(--rose)";
}

function gopLabel(gop: number): string {
  if (gop > -1.0) return "correct";
  if (gop > -2.0) return "marginal";
  return "incorrect";
}

export default function PhonemeTimeline({ phonemes }: Props) {
  if (phonemes.length === 0) return null;

  return (
    <div className="result-enter w-full">
      <p className="mb-3 text-xs font-medium uppercase tracking-widest" style={{ color: "var(--ink-4)" }}>
        Phoneme timeline
      </p>

      {/* Scrollable horizontal strip */}
      <div
        className="flex gap-1 overflow-x-auto pb-3"
        style={{ scrollbarWidth: "none" }}
        aria-label="Phoneme-by-phoneme accuracy"
      >
        {phonemes.map((p, i) => {
          const color = gopColor(p.gop);
          const label = gopLabel(p.gop);
          return (
            <div
              key={i}
              className="flex shrink-0 flex-col items-center gap-1"
              title={
                p.correct
                  ? `/${p.phoneme}/ — correct`
                  : p.substitution
                  ? `${p.substitution} — substitution`
                  : `/${p.phoneme}/ — ${label}`
              }
            >
              {/* Colour pip */}
              <span
                className="flex items-center justify-center rounded"
                style={{
                  width: 28, height: 28,
                  background: color + "22",
                  border: `1.5px solid ${color}`,
                  fontSize: 11,
                  fontFamily: "var(--font-sans)",
                  color: color,
                  fontWeight: 600,
                  lineHeight: 1,
                }}
              >
                {p.phoneme}
              </span>

              {/* Error label underneath */}
              {!p.correct && p.substitution && (
                <span style={{ fontSize: 9, color: "var(--rose)", lineHeight: 1 }}>
                  {p.substitution.split("→")[0]}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex gap-4 mt-1" style={{ fontSize: 11, color: "var(--ink-4)" }}>
        {[
          { color: "var(--jade)", label: "Correct" },
          { color: "var(--accent)", label: "Marginal" },
          { color: "var(--rose)", label: "Needs work" },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              className="inline-block rounded-full"
              style={{ width: 7, height: 7, background: color }}
            />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
