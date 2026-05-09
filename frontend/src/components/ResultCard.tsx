"use client";

import { useEffect, useState } from "react";
import type { ScoreResponse } from "@/lib/types";
import { DimensionBar } from "./DimensionBar";

export function ResultCard({
  result,
  canPlayUser,
  onRetry,
  onPlayUser,
  onPlayReference,
  isPlayingNative,
  isPlayingUser,
}: {
  result: ScoreResponse;
  canPlayUser: boolean;
  onRetry: () => void;
  onPlayUser: () => void;
  onPlayReference: () => void;
  isPlayingNative: boolean;
  isPlayingUser: boolean;
}) {
  const [score, setScore] = useState(0);

  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const duration = 900;
    const tick = (now: number) => {
      const t = Math.max(0, Math.min(1, (now - start) / duration));
      const eased = 1 - Math.pow(1 - t, 3);
      setScore(Math.round(result.finalScore * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [result.finalScore]);

  const min = Math.min(result.mfccScore, result.pitchScore, result.energyScore);
  const weakest =
    min === result.mfccScore ? "clarity" :
    min === result.pitchScore ? "pitch" :
    "energy";

  const grade = gradeFor(result.finalScore);

  return (
    <article className="result-enter flex flex-col gap-7 rounded-2xl border border-line bg-surface/60 p-5 backdrop-blur-sm sm:p-7">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-3">
            Your reading
          </span>
          <p className="text-[14px] leading-snug text-ink-2">
            &ldquo;{result.transcript}&rdquo;
          </p>
        </div>
        <div className="flex flex-col items-end leading-none">
          <span className="text-[40px] font-semibold tabular-nums tracking-tight text-ink">
            {score}
          </span>
          <span className="mt-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-3">
            {grade}
          </span>
        </div>
      </header>

      <div className="flex flex-col gap-5">
        <DimensionBar
          label="Clarity"
          caption="How crisply each consonant and vowel was articulated"
          value={result.mfccScore}
          delay={0}
          weakest={weakest === "clarity"}
        />
        <DimensionBar
          label="Pitch"
          caption="How well your intonation matched the natural rise and fall"
          value={result.pitchScore}
          delay={120}
          weakest={weakest === "pitch"}
        />
        <DimensionBar
          label="Energy"
          caption="How steady your volume and stress placement were"
          value={result.energyScore}
          delay={240}
          weakest={weakest === "energy"}
        />
      </div>

      <div className="rounded-xl border border-accent/25 bg-accent/[0.06] p-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent/90">
          What to fix
        </p>
        <p className="mt-1.5 text-[15px] font-medium leading-snug text-ink">
          {result.feedback}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <ActionButton variant="primary" onClick={onRetry} icon={<RetryIcon />}>
          Try again
        </ActionButton>
        <ActionButton onClick={onPlayReference} icon={<PlayIcon playing={isPlayingNative} />}>
          Native
        </ActionButton>
        <ActionButton
          onClick={onPlayUser}
          disabled={!canPlayUser}
          icon={<PlayIcon playing={isPlayingUser} />}
        >
          Yours
        </ActionButton>
      </div>
    </article>
  );
}

function ActionButton({
  children,
  onClick,
  icon,
  variant = "secondary",
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  icon?: React.ReactNode;
  variant?: "primary" | "secondary";
  disabled?: boolean;
}) {
  const base =
    "press inline-flex cursor-pointer items-center gap-2 rounded-full px-3.5 py-2 text-[13px] font-medium tracking-tight transition-colors";
  const styles =
    variant === "primary"
      ? "bg-ink text-bg hover:bg-ink/90"
      : "border border-line bg-surface/60 text-ink-2 hover-lift";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[base, styles, disabled ? "opacity-40 cursor-not-allowed" : ""].join(" ")}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}

function gradeFor(score: number) {
  if (score >= 90) return "Native-like";
  if (score >= 80) return "Strong";
  if (score >= 70) return "Solid";
  if (score >= 60) return "Getting there";
  if (score >= 50) return "Practice more";
  return "Try again";
}

function RetryIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden>
      <path
        d="M3 8a5 5 0 1 0 1.6-3.66M3 3v3h3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

function PlayIcon({ playing }: { playing: boolean }) {
  if (playing) {
    return (
      <svg width="11" height="11" viewBox="0 0 11 11" aria-hidden>
        <rect x="2" y="2" width="2.4" height="7" fill="currentColor" rx="0.6" />
        <rect x="6.6" y="2" width="2.4" height="7" fill="currentColor" rx="0.6" />
      </svg>
    );
  }
  return (
    <svg width="11" height="11" viewBox="0 0 11 11" aria-hidden>
      <path d="M3 2L9 5.5L3 9V2Z" fill="currentColor" />
    </svg>
  );
}
