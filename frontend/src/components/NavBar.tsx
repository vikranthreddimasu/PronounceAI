"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getStreak, subscribeStorage } from "@/lib/store";
import { tap } from "@/lib/sounds";

type RailItem = {
  href: string;
  label: string;
  meta: string;
  aliases?: string[];
};

const PRIMARY_NAV: RailItem[] = [
  {
    href: "/studio",
    label: "Voice Lab",
    meta: "Your voice, any accent",
    aliases: ["/studio"],
  },
  {
    href: "/practice",
    label: "Practice",
    meta: "Record and score",
    aliases: ["/practice"],
  },
  {
    href: "/progress",
    label: "Progress",
    meta: "History and weak sounds",
    aliases: ["/progress", "/history"],
  },
];

function isActive(path: string, href: string, aliases?: string[]): boolean {
  return path === href || Boolean(aliases?.some((alias) => path.startsWith(alias)));
}

export default function NavBar() {
  const path = usePathname();
  const [streak, setStreak] = useState(0);

  useEffect(() => {
    const sync = () => setStreak(getStreak().current);
    sync();
    return subscribeStorage(sync);
  }, []);

  if (path === "/") return null;

  return (
    <>
      <aside className="notebook-rail" aria-label="Main navigation">
        <Link
          href="/studio"
          className="rail-brand press"
          onClick={() => tap()}
          aria-label="PronounceAI session"
        >
          <span className="brand-mark" aria-hidden>
            <Mark />
          </span>
          <span>
            <strong>PronounceAI</strong>
            <small>Local AI speech lab</small>
          </span>
        </Link>

        <nav className="rail-section" aria-label="Main">
          <p className="rail-kicker">Main</p>
          {PRIMARY_NAV.map((item) => (
            <RailLink key={item.href} item={item} active={isActive(path, item.href, item.aliases)} />
          ))}
        </nav>

        <div className="rail-bottom">
          {streak > 0 && (
            <span className="rail-streak" title={`${streak}-day streak`}>
              {streak}d streak
            </span>
          )}
          <Link
            href="/settings"
            className="rail-settings press"
            data-active={path.startsWith("/settings")}
            onClick={() => tap()}
            aria-label="Settings"
          >
            <SettingsIcon />
            <span>Settings</span>
          </Link>
        </div>
      </aside>

      <header className="mobile-nav-paper">
        <div className="mobile-nav-top">
          <Link
            href="/studio"
            className="press flex items-center"
            onClick={() => tap()}
            style={{ gap: 10, color: "var(--ink)", minWidth: 0 }}
            aria-label="PronounceAI session"
          >
            <span className="brand-mark" aria-hidden>
              <Mark />
            </span>
            <span className="font-display" style={{ fontSize: 17, fontWeight: 680, letterSpacing: 0 }}>
              PronounceAI
            </span>
          </Link>
          <Link
            href="/settings"
            className="icon-button press"
            data-active={path.startsWith("/settings")}
            onClick={() => tap()}
            aria-label="Settings"
            title="Settings"
          >
            <SettingsIcon />
          </Link>
        </div>
        <nav className="mobile-nav-row no-scrollbar" aria-label="Mobile navigation">
          {PRIMARY_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => tap()}
              className="nav-link"
              data-active={isActive(path, item.href, item.aliases)}
              aria-current={isActive(path, item.href, item.aliases) ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
    </>
  );
}

function RailLink({
  item,
  active,
}: {
  item: RailItem;
  active: boolean;
}) {
  return (
    <Link
      href={item.href}
      onClick={() => tap()}
      className="rail-link press"
      data-active={active}
      aria-current={active ? "page" : undefined}
    >
      <span className="rail-dot" aria-hidden />
      <span>
        <strong>{item.label}</strong>
        <small>{item.meta}</small>
      </span>
    </Link>
  );
}

function Mark() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12a7 7 0 0 1 7-7 7 7 0 0 1 7 7 7 7 0 0 1-7 7" />
      <path d="M9 12a3 3 0 0 1 3-3 3 3 0 0 1 3 3 3 3 0 0 1-3 3" />
      <path d="M12 12h7" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.05.05a2 2 0 1 1-2.83 2.83l-.05-.05a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 0 1-4 0v-.07a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.05.05a2 2 0 1 1-2.83-2.83l.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 0 1 0-4h.04A1.7 1.7 0 0 0 4.6 8a1.7 1.7 0 0 0-.34-1.88l-.05-.05a2 2 0 1 1 2.83-2.83l.05.05A1.7 1.7 0 0 0 8.97 3.6 1.7 1.7 0 0 0 10 2.04V2a2 2 0 0 1 4 0v.04a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.05-.05a2 2 0 1 1 2.83 2.83l-.05.05A1.7 1.7 0 0 0 19.4 8c.21.6.79 1 1.42 1H21a2 2 0 0 1 0 4h-.18c-.63 0-1.21.4-1.42 1Z" />
    </svg>
  );
}
