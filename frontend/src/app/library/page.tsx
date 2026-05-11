"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PHRASES, CATEGORY_LABELS } from "@/lib/phrases";
import type { Phrase } from "@/lib/types";
import { tap } from "@/lib/sounds";
import Tabs, { type TabItem } from "@/components/Tabs";

type Filter = "all" | Phrase["category"] | "free";

const TABS: TabItem<Filter>[] = [
  { id: "all", label: "All", count: PHRASES.length },
  {
    id: "minimal-pair",
    label: "Minimal pairs",
    count: PHRASES.filter((p) => p.category === "minimal-pair").length,
  },
  {
    id: "phoneme-drill",
    label: "Phoneme drills",
    count: PHRASES.filter((p) => p.category === "phoneme-drill").length,
  },
  {
    id: "connected-speech",
    label: "Connected speech",
    count: PHRASES.filter((p) => p.category === "connected-speech").length,
  },
  {
    id: "authentic",
    label: "Authentic",
    count: PHRASES.filter((p) => p.category === "authentic").length,
  },
  { id: "free", label: "Free speak" },
];

function focusLabel(focus: string): string {
  if (focus.includes("-vs-")) {
    const [a, b] = focus.split("-vs-");
    return `/${a}/ vs /${b}/`;
  }
  return focus.replace(/-/g, " ");
}

export default function LibraryPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const list = useMemo(() => {
    let pool = filter === "all" || filter === "free" ? PHRASES : PHRASES.filter((p) => p.category === filter);
    if (query.trim()) {
      const q = query.toLowerCase();
      pool = pool.filter(
        (p) => p.text.toLowerCase().includes(q) || p.focus.toLowerCase().includes(q)
      );
    }
    return pool;
  }, [filter, query]);

  return (
    <main className="mx-auto" style={{ maxWidth: 1080, padding: "32px 20px 80px" }}>
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
          Library
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
          What do you want to practice?
        </h1>
      </header>

      <div className="flex flex-wrap" style={{ gap: 12, marginBottom: 24 }}>
        <Tabs items={TABS} active={filter} onChange={setFilter} ariaLabel="Phrase category" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search phrases or focus…"
          className="font-mono"
          style={{
            flex: "1 1 240px",
            minWidth: 200,
            padding: "9px 14px",
            borderRadius: 10,
            border: "1px solid var(--line)",
            background: "var(--paper)",
            color: "var(--ink-2)",
            fontSize: 12,
            outline: "none",
          }}
        />
      </div>

      {filter === "free" ? (
        <div className="card-paper" style={{ padding: 24, display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <p
            className="font-display"
            style={{ fontSize: 18, fontWeight: 600, color: "var(--ink)", flex: 1, minWidth: 200, margin: 0, letterSpacing: "-0.01em" }}
          >
            Type → record → score. No fixed prompts.
          </p>
          <Link
            href="/practice"
            onClick={() => tap()}
            className="btn-paper btn-primary press"
            style={{ fontSize: 13 }}
          >
            Open free speak →
          </Link>
        </div>
      ) : (
        <div
          className="grid"
          style={{ gap: 14, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}
        >
          {list.map((p, i) => (
            <Link
              key={p.id}
              href={`/practice?phrase=${encodeURIComponent(p.id)}`}
              onClick={() => tap()}
              className="card-paper-flat press"
              style={{
                padding: "18px 18px 16px",
                textDecoration: "none",
                color: "var(--ink)",
                display: "block",
                animation: `rise 600ms var(--ease-paper) ${Math.min(i * 18, 480)}ms both`,
                opacity: 0,
              }}
            >
              <div className="flex items-center" style={{ gap: 8, marginBottom: 10 }}>
                <span className="tag">{CATEGORY_LABELS[p.category]}</span>
                <span className="tag tag-accent">{focusLabel(p.focus)}</span>
              </div>
              <p
                className="font-display"
                style={{
                  fontSize: 17,
                  fontWeight: 600,
                  lineHeight: 1.35,
                  color: "var(--ink)",
                  letterSpacing: "-0.01em",
                }}
              >
                {p.text}
              </p>
            </Link>
          ))}
          {list.length === 0 && (
            <p style={{ color: "var(--ink-3)", fontSize: 13 }}>No phrases match.</p>
          )}
        </div>
      )}
    </main>
  );
}
