"use client";

import type { PhonemeResult } from "@/lib/types";

type Props = { phonemes: PhonemeResult[] };

function gopColor(gop: number): string {
  if (gop > -1.0) return "var(--jade)";
  if (gop > -2.0) return "var(--ink)";
  return "var(--accent)";
}

function gopLabel(gop: number): string {
  if (gop > -1.0) return "correct";
  if (gop > -2.0) return "marginal";
  return "incorrect";
}

export default function PhonemeTimeline({ phonemes }: Props) {
  if (phonemes.length === 0) return null;

  return (
    <div className="result-enter w-full" style={{ borderTop: "1px solid var(--rule)", paddingTop: 14 }}>
      <p className="eyebrow" style={{ marginBottom: 12 }}>
        Phoneme Timeline
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
              className="phoneme-pip-wrap flex shrink-0 flex-col items-center gap-1 fade-pop"
              style={{ animationDelay: `${Math.min(i * 28, 600)}ms` }}
              title={
                p.correct
                  ? `/${p.phoneme}/: correct`
                  : p.substitution
                  ? `${p.substitution}: substitution`
                  : `/${p.phoneme}/: ${label}`
              }
            >
              <span
                className="phoneme-pip flex items-center justify-center"
                style={{
                  width: 30, height: 30,
                  background: "transparent",
                  border: `1px solid ${color}`,
                  borderRadius: 0,
                  fontFamily: "var(--type-mono)",
                  fontSize: 11,
                  color: color,
                  fontWeight: 600,
                  letterSpacing: 0,
                  lineHeight: 1,
                  transition: "transform 180ms var(--ease-out), background-color 180ms var(--ease-out)",
                  cursor: "pointer",
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
      <div
        className="flex gap-4 mt-1"
        style={{
          fontFamily: "var(--type-mono)",
          fontSize: 10,
          color: "var(--ink-4)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        {[
          { color: "var(--jade)", label: "Correct" },
          { color: "var(--ink)", label: "Marginal" },
          { color: "var(--accent)", label: "Needs work" },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1.5">
            <span
              className="inline-block"
              style={{ width: 7, height: 7, background: color, borderRadius: 0 }}
            />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
