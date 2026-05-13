"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getStreak, subscribeStorage } from "@/lib/store";
import { tap } from "@/lib/sounds";

type NavItem = {
  href: string;
  label: string;
  aliases?: string[];
};

const PRIMARY_NAV: NavItem[] = [
  { href: "/studio", label: "Voice Lab" },
  { href: "/practice", label: "Practice" },
  { href: "/progress", label: "Progress", aliases: ["/progress", "/history"] },
  { href: "/settings", label: "Settings" },
];

function isActive(path: string, href: string, aliases?: string[]): boolean {
  return path === href || Boolean(aliases?.some((alias) => path.startsWith(alias)));
}

function sectionLabel(path: string): string {
  if (path.startsWith("/studio")) return "Voice Lab";
  if (path.startsWith("/practice")) return "Practice";
  if (path.startsWith("/progress") || path.startsWith("/history")) return "Progress";
  if (path.startsWith("/settings")) return "Settings";
  if (path.startsWith("/library")) return "Library";
  return "Session";
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

  const section = sectionLabel(path);

  return (
    <header className="editorial-bar" aria-label="Main navigation">
      <div className="editorial-bar-inner">
        <Link
          href="/studio"
          className="editorial-wordmark press"
          onClick={() => tap()}
          aria-label="PronounceAI home"
        >
          <span>
            Pronounce<em>·</em>AI
          </span>
          <span className="meta">{section}</span>
        </Link>

        <nav className="editorial-nav" aria-label="Sections">
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
          {streak > 0 && (
            <span className="editorial-streak" title={`${streak}-day streak`}>
              <strong>{streak}</strong>d streak
            </span>
          )}
        </nav>
      </div>
    </header>
  );
}
