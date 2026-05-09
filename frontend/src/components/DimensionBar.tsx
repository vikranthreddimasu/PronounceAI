"use client";

import { useEffect, useRef, useState } from "react";

export function DimensionBar({
  label,
  caption,
  value,
  delay = 0,
  weakest = false,
}: {
  label: string;
  caption: string;
  value: number;
  delay?: number;
  weakest?: boolean;
}) {
  const [displayed, setDisplayed] = useState(0);
  const fillRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const el = fillRef.current;
    if (!el) return;
    el.style.setProperty("--tone", toneFor(value));
    el.style.setProperty("--delay", `${delay}ms`);
    el.style.setProperty("--pct", "0%");
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.setProperty("--pct", `${Math.max(0, Math.min(100, value))}%`);
      });
    });
  }, [value, delay]);

  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const duration = 900;
    const tick = (now: number) => {
      const t = Math.max(0, Math.min(1, (now - start - delay) / duration));
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayed(Math.round(value * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, delay]);

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="text-[13px] font-semibold tracking-tight text-ink">
            {label}
          </span>
          {weakest ? (
            <span className="rounded-full bg-warn/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
              fix this
            </span>
          ) : null}
        </div>
        <span className="text-[15px] font-semibold tabular-nums tracking-tight text-ink">
          {displayed}
          <span className="ml-0.5 text-[11px] font-medium text-ink-4">/100</span>
        </span>
      </div>
      <div className="dim-track">
        <span ref={fillRef} className="dim-fill" />
      </div>
      <p className="text-[12px] leading-snug text-ink-3">{caption}</p>
    </div>
  );
}

function toneFor(score: number): string {
  if (score >= 80) return "var(--jade)";
  if (score >= 60) return "var(--accent)";
  return "var(--rose)";
}
