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

function relativeDate(ms: number): string {
  const diff = Date.now() - ms;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  const days = Math.floor(diff / 86_400_000);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return new Date(ms).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

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

  const avgScore = sessions.length > 0
    ? Math.round(sessions.reduce((sum, session) => sum + session.overall, 0) / sessions.length)
    : 0;

  const soundQueue = useMemo(() => {
    return Object.entries(stats)
      .map(([ipa, stat]) => ({ ipa, stat, mastery: masteryOf(stat) }))
      .filter((item) => item.stat.attempts > 0)
      .sort((a, b) => a.mastery - b.mastery)
      .slice(0, 8);
  }, [stats]);

  if (sessions.length === 0) {
    return (
      <main className="notebook-page">
        <section className="empty-notebook">
          <p className="eyebrow">Progress</p>
          <h1>Nothing to analyze yet.</h1>
          <p>
            After one recording, this becomes a quiet record of attempts, weak sounds, and the next useful practice target.
          </p>
          <Link href="/practice" onClick={() => tap()} className="btn-paper btn-primary press">
            Start a session
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="notebook-page">
      <section className="notebook-header">
        <div>
          <p className="eyebrow">Progress</p>
          <h1>What changed?</h1>
        </div>
        <Link href="/practice" onClick={() => tap()} className="btn-paper press">
          New session
        </Link>
      </section>

      <section className="notebook-grid">
        <article className="attempt-ledger" aria-label="Recent attempts">
          <header>
            <p className="eyebrow">Recent attempts</p>
            <p>{sessions.length} total recordings</p>
          </header>
          <div className="attempt-list">
            {sessions.slice(0, 14).map((session) => (
              <SessionRow key={session.id} session={session} />
            ))}
          </div>
        </article>

        <aside className="notebook-aside">
          <div className="notebook-summary">
            <p className="eyebrow">Current signal</p>
            <strong>{avgScore}</strong>
            <span>average score</span>
          </div>
          <div className="notebook-facts">
            <Fact label="Streak" value={`${streak.current} day${streak.current === 1 ? "" : "s"}`} />
            <Fact label="Longest" value={`${streak.longest} day${streak.longest === 1 ? "" : "s"}`} />
            <Fact label="Sounds seen" value={Object.keys(stats).length.toString()} />
          </div>

          <section className="sound-queue">
            <p className="eyebrow">Revisit next</p>
            {soundQueue.length === 0 ? (
              <p>No phoneme history yet.</p>
            ) : (
              <div>
                {soundQueue.map(({ ipa, mastery, stat }) => (
                  <div key={ipa} className="sound-row">
                    <span>/{ipa}/</span>
                    <meter min={0} max={1} value={mastery} aria-label={`Mastery for ${ipa}`} />
                    <small>{stat.attempts}x</small>
                  </div>
                ))}
              </div>
            )}
          </section>
        </aside>
      </section>

      <details className="analysis-fold notebook-fold">
        <summary>
          <span>Trend</span>
          <small>last 30 scores</small>
        </summary>
        <ScoreChart sessions={sessions.slice(0, 30).slice().reverse()} />
      </details>
    </main>
  );
}

function SessionRow({ session }: { session: Session }) {
  const tone = session.overall >= 80 ? "var(--jade)" : session.overall >= 65 ? "var(--ink)" : "var(--accent)";
  return (
    <article className="attempt-row">
      <span className="attempt-score" style={{ color: tone, borderColor: tone }}>
        {Math.round(session.overall)}
      </span>
      <div>
        <p>{session.phrase}</p>
        <small>
          {relativeDate(session.date)} · {session.accent}
          {session.worstPhoneme ? ` · /${session.worstPhoneme}/` : ""}
        </small>
      </div>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ScoreChart({ sessions }: { sessions: Session[] }) {
  if (sessions.length === 0) return <p className="section-copy">Not enough sessions yet.</p>;

  const viewW = 900;
  const viewH = 210;
  const padX = 18;
  const padY = 22;
  const stepX = sessions.length > 1 ? (viewW - padX * 2) / (sessions.length - 1) : 0;
  const yFromScore = (score: number) => padY + (viewH - padY * 2) * (1 - score / 100);
  const linePath = sessions
    .map((session, index) => {
      const x = padX + index * stepX;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${yFromScore(session.overall).toFixed(1)}`;
    })
    .join(" ");

  return (
    <div style={{ padding: 18 }}>
      <svg viewBox={`0 0 ${viewW} ${viewH}`} width="100%" height={viewH} preserveAspectRatio="none" aria-label="Overall score trend">
        {[50, 75].map((score) => (
          <line
            key={score}
            x1={padX}
            x2={viewW - padX}
            y1={yFromScore(score)}
            y2={yFromScore(score)}
            stroke="var(--line)"
            strokeDasharray="3 6"
          />
        ))}
        <path d={linePath} fill="none" stroke="var(--accent)" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        {sessions.map((session, index) => (
          <circle
            key={session.id}
            cx={padX + index * stepX}
            cy={yFromScore(session.overall)}
            r={3}
            fill="var(--paper)"
            stroke="var(--accent)"
            strokeWidth={1.5}
          />
        ))}
      </svg>
    </div>
  );
}
