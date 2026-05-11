"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  getSessions,
  getPhonemeStats,
  getStreak,
  masteryOf,
  subscribeStorage,
  type Session,
  type PhonemeStat,
  type Streak,
} from "@/lib/store";
import { tap } from "@/lib/sounds";

export default function ProgressPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [stats, setStats] = useState<Record<string, PhonemeStat>>({});
  const [streak, setStreak] = useState<Streak>({ current: 0, longest: 0, lastSessionDate: null });

  useEffect(() => {
    const sync = () => {
      setSessions(getSessions());
      setStats(getPhonemeStats());
      setStreak(getStreak());
    };
    sync();
    return subscribeStorage(sync);
  }, []);

  const totalAttempts = sessions.length;
  const avgScore = totalAttempts > 0
    ? Math.round(sessions.reduce((a, s) => a + s.overall, 0) / totalAttempts)
    : 0;
  const last7 = useMemo(() => {
    const cutoff = Date.now() - 7 * 86_400_000;
    return sessions.filter((s) => s.date >= cutoff);
  }, [sessions]);

  // Empty state
  if (totalAttempts === 0) {
    return (
      <main className="mx-auto" style={{ maxWidth: 720, padding: "80px 24px", textAlign: "center" }}>
        <p
          className="font-mono"
          style={{
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--ink-4)",
            marginBottom: 8,
          }}
        >
          Progress
        </p>
        <h1
          className="font-display"
          style={{
            fontSize: 36,
            fontWeight: 700,
            color: "var(--ink)",
            letterSpacing: "-0.02em",
            marginBottom: 14,
          }}
        >
          Nothing to show yet.
        </h1>
        <p style={{ color: "var(--ink-3)", fontSize: 14, lineHeight: 1.55, marginBottom: 28 }}>
          Record one phrase and your phoneme mastery, accent score, and streak will start drawing themselves here.
        </p>
        <Link href="/practice" onClick={() => tap()} className="btn-paper btn-primary press" style={{ fontSize: 13 }}>
          Record your first phrase →
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto" style={{ maxWidth: 1080, padding: "32px 20px 80px" }}>
      <header style={{ marginBottom: 32 }}>
        <p
          className="font-mono"
          style={{
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--ink-4)",
            marginBottom: 6,
          }}
        >
          Progress
        </p>
        <h1
          className="font-display"
          style={{
            fontSize: 36,
            fontWeight: 700,
            color: "var(--ink)",
            letterSpacing: "-0.02em",
          }}
        >
          The signal, over time.
        </h1>
      </header>

      {/* Stat tiles */}
      <div
        className="grid"
        style={{ gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginBottom: 32 }}
      >
        <StatTile label="Sessions" value={totalAttempts.toString()} />
        <StatTile label="Average score" value={`${avgScore}`} suffix=" / 100" />
        <StatTile label="This week" value={last7.length.toString()} />
        <StatTile label="Streak" value={streak.current.toString()} suffix="d" extra={`longest ${streak.longest}d`} />
      </div>

      {/* Score over time chart */}
      <section className="card-paper" style={{ padding: 24, marginBottom: 24 }}>
        <header style={{ marginBottom: 18 }}>
          <p
            className="font-mono"
            style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-4)" }}
          >
            Overall score
          </p>
          <h3
            className="font-display"
            style={{ fontSize: 20, fontWeight: 600, color: "var(--ink)", letterSpacing: "-0.01em", marginTop: 2 }}
          >
            Last 30 sessions
          </h3>
        </header>
        <ScoreChart sessions={sessions.slice(0, 30).slice().reverse()} />
      </section>

      {/* Phoneme heatmap */}
      <section className="card-paper" style={{ padding: 24 }}>
        <header style={{ marginBottom: 18 }}>
          <p
            className="font-mono"
            style={{ fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-4)" }}
          >
            Phoneme mastery
          </p>
          <h3
            className="font-display"
            style={{ fontSize: 20, fontWeight: 600, color: "var(--ink)", letterSpacing: "-0.01em", marginTop: 2 }}
          >
            What you own, what's still loose.
          </h3>
        </header>
        <PhonemeHeatmap stats={stats} />
      </section>
    </main>
  );
}

function StatTile({ label, value, suffix, extra }: { label: string; value: string; suffix?: string; extra?: string }) {
  return (
    <div className="card-paper-flat" style={{ padding: "16px 18px" }}>
      <p
        className="font-mono"
        style={{
          fontSize: 10,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "var(--ink-4)",
          marginBottom: 6,
        }}
      >
        {label}
      </p>
      <p
        className="font-display"
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: "var(--ink)",
          letterSpacing: "-0.02em",
          lineHeight: 1.05,
        }}
      >
        {value}
        {suffix && (
          <span style={{ fontSize: 14, color: "var(--ink-4)", fontWeight: 500, marginLeft: 2 }}>{suffix}</span>
        )}
      </p>
      {extra && (
        <p style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 6 }}>{extra}</p>
      )}
    </div>
  );
}

function ScoreChart({ sessions }: { sessions: Session[] }) {
  if (sessions.length === 0) {
    return <p style={{ color: "var(--ink-3)", fontSize: 13 }}>Not enough sessions yet.</p>;
  }

  const VIEW_W = 880;
  const VIEW_H = 200;
  const PAD_X = 16;
  const PAD_Y = 20;
  const n = sessions.length;
  const stepX = n > 1 ? (VIEW_W - PAD_X * 2) / (n - 1) : 0;
  const yFromScore = (s: number) =>
    PAD_Y + (VIEW_H - PAD_Y * 2) * (1 - s / 100);

  const linePath = sessions
    .map((s, i) => {
      const x = PAD_X + i * stepX;
      const y = yFromScore(s.overall);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const areaPath =
    linePath +
    ` L${(PAD_X + (n - 1) * stepX).toFixed(1)} ${(VIEW_H - PAD_Y).toFixed(1)}` +
    ` L${PAD_X.toFixed(1)} ${(VIEW_H - PAD_Y).toFixed(1)} Z`;

  const gridYs = [25, 50, 75].map(yFromScore);

  return (
    <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" height={VIEW_H} preserveAspectRatio="none">
      <defs>
        <linearGradient id="score-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridYs.map((y, i) => (
        <line
          key={i}
          x1={PAD_X}
          x2={VIEW_W - PAD_X}
          y1={y}
          y2={y}
          stroke="var(--line)"
          strokeDasharray="3 5"
          opacity={0.55}
        />
      ))}
      <path d={areaPath} fill="url(#score-fill)" />
      <path d={linePath} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {sessions.map((s, i) => (
        <circle
          key={s.id}
          cx={PAD_X + i * stepX}
          cy={yFromScore(s.overall)}
          r={2.6}
          fill="var(--paper)"
          stroke="var(--accent)"
          strokeWidth={1.5}
        />
      ))}
    </svg>
  );
}

function PhonemeHeatmap({ stats }: { stats: Record<string, PhonemeStat> }) {
  const sorted = Object.entries(stats)
    .map(([ipa, s]) => ({ ipa, mastery: masteryOf(s), attempts: s.attempts }))
    .sort((a, b) => a.mastery - b.mastery);

  if (sorted.length === 0) {
    return <p style={{ color: "var(--ink-3)", fontSize: 13 }}>No phoneme data yet.</p>;
  }

  return (
    <div className="grid" style={{ gap: 8, gridTemplateColumns: "repeat(auto-fill, minmax(58px, 1fr))" }}>
      {sorted.map(({ ipa, mastery, attempts }) => {
        const color =
          mastery >= 0.75 ? "var(--jade)" : mastery >= 0.5 ? "var(--accent)" : "var(--rose)";
        return (
          <div
            key={ipa}
            title={`/${ipa}/ — mastery ${(mastery * 100).toFixed(0)}% over ${attempts} attempts`}
            style={{
              borderRadius: 10,
              padding: "10px 8px",
              background: color + "1a",
              border: `1px solid ${color}55`,
              textAlign: "center",
            }}
          >
            <p
              className="font-display"
              style={{ fontSize: 18, fontWeight: 700, color, lineHeight: 1, letterSpacing: 0 }}
            >
              {ipa}
            </p>
            <p
              className="font-mono"
              style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 4, letterSpacing: 0 }}
            >
              {Math.round(mastery * 100)}
            </p>
          </div>
        );
      })}
    </div>
  );
}
