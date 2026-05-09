"use client";

import type { Phrase } from "@/lib/types";

const DIFFICULTY_DOTS: Record<Phrase["difficulty"], number> = {
  easy: 1,
  medium: 2,
  hard: 3,
};

export function PhraseStage({
  phrase,
  index,
  total,
  onPlayNative,
  isPlayingNative,
}: {
  phrase: Phrase;
  index: number;
  total: number;
  onPlayNative: () => void;
  isPlayingNative: boolean;
}) {

  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-center justify-between text-[11px] font-medium uppercase tracking-[0.18em] text-ink-3">
        <span className="flex items-center gap-2">
          <DifficultyDots level={DIFFICULTY_DOTS[phrase.difficulty]} />
          <span>{phrase.difficulty}</span>
        </span>
        <span className="tabular-nums text-ink-4">
          {String(index + 1).padStart(2, "0")}
          <span className="px-1">/</span>
          {String(total).padStart(2, "0")}
        </span>
      </div>

      <p
        key={phrase.id}
        className="phrase-mount font-display text-[clamp(2rem,6.4vw,3.25rem)] font-medium leading-[1.08] tracking-tight text-ink"
        aria-live="polite"
      >
        &ldquo;{phrase.text}&rdquo;
      </p>

      <button
        type="button"
        onClick={onPlayNative}
        className="press hover-accent group inline-flex w-fit cursor-pointer items-center gap-2.5 rounded-full border border-line bg-surface/40 px-3.5 py-2 text-[12.5px] font-medium text-ink-2"
      >
        <span
          className={[
            "grid h-6 w-6 place-items-center rounded-full text-accent transition-colors",
            isPlayingNative ? "bg-accent/20" : "bg-accent/10 group-hover:bg-accent/20",
          ].join(" ")}
        >
          {isPlayingNative ? (
            <svg width="9" height="9" viewBox="0 0 9 9" aria-hidden>
              <rect x="1.5" y="1.5" width="2" height="6" fill="currentColor" rx="0.5" />
              <rect x="5.5" y="1.5" width="2" height="6" fill="currentColor" rx="0.5" />
            </svg>
          ) : (
            <svg width="9" height="9" viewBox="0 0 10 10" aria-hidden>
              <path d="M2.5 1.5L8 5L2.5 8.5V1.5Z" fill="currentColor" />
            </svg>
          )}
        </span>
        Hear native speaker
      </button>
    </section>
  );
}

function DifficultyDots({ level }: { level: number }) {
  return (
    <span aria-hidden className="inline-flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={[
            "block h-1 w-1 rounded-full",
            i < level ? "bg-accent" : "bg-ink-5",
          ].join(" ")}
        />
      ))}
    </span>
  );
}
