"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { PHRASES, CATEGORY_LABELS } from "@/lib/phrases";
import { tap } from "@/lib/sounds";

function focusLabel(focus: string): string {
  if (focus.includes("-vs-")) {
    const [a, b] = focus.split("-vs-");
    return `/${a}/ vs /${b}/`;
  }
  return focus.replace(/-/g, " ");
}

export default function LibraryPage() {
  const [query, setQuery] = useState("");

  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return PHRASES;
    return PHRASES.filter(
      (phrase) =>
        phrase.text.toLowerCase().includes(q) ||
        phrase.focus.toLowerCase().includes(q) ||
        CATEGORY_LABELS[phrase.category].toLowerCase().includes(q)
    );
  }, [query]);

  return (
    <main className="shelf-page">
      <section className="shelf-header">
        <div>
          <p className="eyebrow">Phrase shelf</p>
          <h1>Choose one line, then return to the session.</h1>
        </div>
        <Link href="/practice" onClick={() => tap()} className="btn-paper press">
          Back to session
        </Link>
      </section>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="shelf-search"
        placeholder="Search sound, phrase, or category"
        aria-label="Search phrase shelf"
      />

      <section className="shelf-list" aria-label="Practice phrases">
        {list.map((phrase) => (
          <Link
            key={phrase.id}
            href={`/practice?phrase=${encodeURIComponent(phrase.id)}`}
            onClick={() => tap()}
            className="shelf-row press"
          >
            <span>{phrase.text}</span>
            <small>
              {CATEGORY_LABELS[phrase.category]} · {focusLabel(phrase.focus)}
            </small>
          </Link>
        ))}
        {list.length === 0 && (
          <p className="section-copy">No phrase matches that search.</p>
        )}
      </section>
    </main>
  );
}
