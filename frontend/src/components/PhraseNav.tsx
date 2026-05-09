export function PhraseNav({
  onPrev,
  onNext,
  onShuffle,
}: {
  onPrev: () => void;
  onNext: () => void;
  onShuffle: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <NavButton onClick={onPrev} aria-label="Previous phrase">
        <ChevronIcon direction="left" />
        <span>Previous</span>
      </NavButton>

      <button
        type="button"
        onClick={onShuffle}
        aria-label="Shuffle to a random phrase"
        className="press hover-accent inline-grid h-10 w-10 cursor-pointer place-items-center rounded-full border border-line bg-surface/40 text-ink-3"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
          <path
            d="M11 3h3v3M14 3l-3.5 3.5M11 13h3v-3M14 13l-3.5-3.5M2 3.5h2.5l8 9H15"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </button>

      <NavButton onClick={onNext} aria-label="Next phrase">
        <span>Next</span>
        <ChevronIcon direction="right" />
      </NavButton>
    </div>
  );
}

function NavButton({
  children,
  onClick,
  ...rest
}: {
  children: React.ReactNode;
  onClick: () => void;
} & React.AriaAttributes) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="press hover-lift inline-flex cursor-pointer items-center gap-2 rounded-full border border-line bg-surface/40 px-4 py-2 text-[13px] font-medium text-ink-2"
      {...rest}
    >
      {children}
    </button>
  );
}

function ChevronIcon({ direction }: { direction: "left" | "right" }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      className={direction === "right" ? "rotate-180" : ""}
      aria-hidden
    >
      <path
        d="M6.5 1.5L2.5 5L6.5 8.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
