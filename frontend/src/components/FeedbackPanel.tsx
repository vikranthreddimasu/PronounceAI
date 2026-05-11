"use client";

import type { FeedbackTip } from "@/lib/types";

type Props = { tips: FeedbackTip[] };

function ms(v: number) {
  const s = Math.floor(v / 1000);
  const t = Math.floor((v % 1000) / 100);
  return `${s}.${t}s`;
}

export default function FeedbackPanel({ tips }: Props) {
  if (!tips.length) return null;

  const [hero, ...rest] = tips;

  return (
    <div className="result-enter flex flex-col" style={{ gap: 10 }}>
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
        Coaching
      </p>

      {/* Hero tip — the most important one */}
      <div
        style={{
          padding: "16px 18px",
          borderRadius: 16,
          background: "var(--surface)",
          border: "1px solid rgba(232,184,95,0.18)",
          boxShadow: "0 0 0 1px transparent, 0 4px 24px -8px rgba(232,184,95,0.12)",
        }}
      >
        <div className="flex gap-3">
          <span
            className="flex items-center justify-center rounded-full text-xs font-bold flex-shrink-0"
            style={{
              width: 22, height: 22, marginTop: 1,
              background: "var(--accent-faint)",
              color: "var(--accent)",
              border: "1px solid rgba(232,184,95,0.3)",
              fontSize: 11,
            }}
          >
            1
          </span>
          <div>
            <p style={{ fontSize: 14, color: "var(--ink)", lineHeight: 1.6 }}>{hero.text}</p>
            {hero.timestamp_ms != null && (
              <p style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 6 }}>at {ms(hero.timestamp_ms)}</p>
            )}
          </div>
        </div>
      </div>

      {/* Secondary tips — more compact */}
      {rest.map((tip, i) => (
        <div
          key={i}
          style={{
            padding: "12px 16px",
            borderRadius: 12,
            background: "var(--surface)",
            border: "1px solid var(--line)",
          }}
        >
          <div className="flex gap-3">
            <span
              className="flex items-center justify-center rounded-full flex-shrink-0"
              style={{
                width: 20, height: 20, marginTop: 1,
                background: "var(--surface-2)",
                color: "var(--ink-4)",
                fontSize: 10,
                fontWeight: 700,
                border: "1px solid var(--line)",
              }}
            >
              {i + 2}
            </span>
            <div>
              <p style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.55 }}>{tip.text}</p>
              {tip.timestamp_ms != null && (
                <p style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>at {ms(tip.timestamp_ms)}</p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
