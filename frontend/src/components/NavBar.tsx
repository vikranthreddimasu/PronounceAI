"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getStreak, subscribeStorage } from "@/lib/store";
import { tap } from "@/lib/sounds";

const LINKS = [
  { href: "/practice", label: "Practice" },
  { href: "/studio", label: "Studio" },
  { href: "/library", label: "Library" },
  { href: "/progress", label: "Progress" },
  { href: "/history", label: "History" },
];

export default function NavBar() {
  const path = usePathname();
  const [streak, setStreak] = useState(0);

  useEffect(() => {
    const sync = () => setStreak(getStreak().current);
    sync();
    return subscribeStorage(sync);
  }, []);

  // Hide on landing — the marketing page has its own header
  if (path === "/") return null;

  return (
    <header
      className="nav-paper sticky top-0"
      style={{ zIndex: 30, paddingInline: "max(20px, env(safe-area-inset-left))" }}
    >
      <div
        className="mx-auto flex items-center justify-between"
        style={{ maxWidth: 1180, height: 60 }}
      >
        <Link
          href="/practice"
          className="press flex items-center"
          onClick={() => tap()}
          style={{ gap: 8, color: "var(--ink)" }}
        >
          <Mark />
          <span
            className="font-display"
            style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em" }}
          >
            PronounceAI
          </span>
        </Link>

        <nav className="hidden md:flex items-center" style={{ gap: 2 }}>
          {LINKS.map((l) => {
            const active = path === l.href || (l.href !== "/practice" && path.startsWith(l.href));
            return (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => tap()}
                className="nav-link"
                data-active={active}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center" style={{ gap: 10 }}>
          {streak > 0 && (
            <span
              className="tag tag-accent"
              title={`${streak}-day streak`}
              aria-label={`${streak} day streak`}
            >
              <span aria-hidden style={{ fontSize: 10 }}>◦</span>
              {streak}d
            </span>
          )}
          <Link
            href="/settings"
            className="press nav-link"
            data-active={path.startsWith("/settings")}
            onClick={() => tap()}
            aria-label="Settings"
          >
            <Gear />
          </Link>
        </div>
      </div>

      {/* Mobile nav — same links, scrollable */}
      <nav
        className="md:hidden no-scrollbar flex items-center"
        style={{
          gap: 2,
          padding: "6px 16px 10px",
          overflowX: "auto",
          borderTop: "1px solid var(--line)",
        }}
      >
        {LINKS.map((l) => {
          const active = path === l.href || (l.href !== "/practice" && path.startsWith(l.href));
          return (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => tap()}
              className="nav-link"
              data-active={active}
              style={{ whiteSpace: "nowrap", flexShrink: 0 }}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}

function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="var(--accent)" />
      <path d="M8 12c0-3 2-5 4-5s4 2 4 5-2 5-4 5" stroke="var(--accent)" />
      <circle cx="16" cy="12" r="1.2" fill="var(--accent)" stroke="none" />
    </svg>
  );
}

function Gear() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
