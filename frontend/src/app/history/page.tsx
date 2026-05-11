"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getSessions, subscribeStorage, type Session } from "@/lib/store";
import { tap } from "@/lib/sounds";

function relativeDate(ms: number): string {
  const d = new Date(ms);
  const diff = Date.now() - ms;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  const days = Math.floor(diff / 86_400_000);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function fmtTime(ms: number): string {
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export default function HistoryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    const sync = () => setSessions(getSessions());
    sync();
    return subscribeStorage(sync);
  }, []);

  const grouped = useMemo(() => {
    const groups: Record<string, Session[]> = {};
    for (const s of sessions) {
      const day = new Date(s.date).toLocaleDateString(undefined, {
        weekday: "long",
        month: "short",
        day: "numeric",
      });
      (groups[day] ??= []).push(s);
    }
    return Object.entries(groups);
  }, [sessions]);

  if (sessions.length === 0) {
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
          History
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
          No sessions yet.
        </h1>
        <Link href="/practice" onClick={() => tap()} className="btn-paper btn-primary press" style={{ fontSize: 13 }}>
          Record your first phrase →
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto" style={{ maxWidth: 880, padding: "32px 20px 80px" }}>
      <header style={{ marginBottom: 28 }}>
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
          History
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
          Every phrase. Every score.
        </h1>
      </header>

      <div className="flex flex-col" style={{ gap: 28 }}>
        {grouped.map(([day, items]) => (
          <section key={day}>
            <p
              className="font-mono"
              style={{
                fontSize: 11,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "var(--ink-4)",
                marginBottom: 10,
              }}
            >
              {day} · {items.length}
            </p>
            <div className="flex flex-col" style={{ gap: 8 }}>
              {items.map((s) => (
                <article
                  key={s.id}
                  className="card-paper-flat"
                  style={{
                    padding: "14px 18px",
                    display: "grid",
                    gridTemplateColumns: "60px minmax(0,1fr) auto",
                    alignItems: "center",
                    gap: 16,
                  }}
                >
                  <ScoreDot value={s.overall} />
                  <div style={{ minWidth: 0 }}>
                    <p
                      className="font-display"
                      style={{
                        fontSize: 15,
                        fontWeight: 600,
                        color: "var(--ink)",
                        letterSpacing: "-0.005em",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {s.phrase}
                    </p>
                    <p
                      className="font-mono"
                      style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4, letterSpacing: 0 }}
                    >
                      {s.accent}
                      <span style={{ margin: "0 6px", opacity: 0.5 }}>·</span>
                      {s.mode === "free" ? "free" : "phrase"}
                      <span style={{ margin: "0 6px", opacity: 0.5 }}>·</span>
                      {fmtTime(s.date)}
                      <span style={{ margin: "0 6px", opacity: 0.5 }}>·</span>
                      {relativeDate(s.date)}
                      {s.worstPhoneme && (
                        <>
                          <span style={{ margin: "0 6px", opacity: 0.5 }}>·</span>
                          <span style={{ color: "var(--rose)" }}>worst /{s.worstPhoneme}/</span>
                        </>
                      )}
                    </p>
                  </div>
                  <p
                    className="font-mono"
                    style={{ fontSize: 11, color: "var(--ink-4)", letterSpacing: 0 }}
                  >
                    {s.phonemeCount} phon.
                  </p>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}

function ScoreDot({ value }: { value: number }) {
  const color = value >= 80 ? "var(--jade)" : value >= 65 ? "var(--accent)" : "var(--rose)";
  return (
    <div
      style={{
        width: 52,
        height: 52,
        borderRadius: "50%",
        border: `2px solid ${color}`,
        background: color + "12",
        color,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <span
        className="font-display"
        style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: "tabular-nums", lineHeight: 1 }}
      >
        {value}
      </span>
    </div>
  );
}
