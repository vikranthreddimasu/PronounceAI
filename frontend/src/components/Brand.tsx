export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      <span className="text-[13px] font-semibold tracking-tight text-ink">
        Pronounce<span className="text-accent">.</span>ai
      </span>
    </div>
  );
}

function BrandMark() {
  return (
    <span
      aria-hidden
      className="grid h-7 w-7 place-items-center rounded-md bg-accent/15 text-accent"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path
          d="M3 5v6M6 3v10M9 6v4M12 4.5v7"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}
