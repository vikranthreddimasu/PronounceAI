import type { Difficulty } from "@/lib/types";

const TABS: { id: Difficulty | "all"; label: string }[] = [
  { id: "all", label: "All" },
  { id: "easy", label: "Easy" },
  { id: "medium", label: "Medium" },
  { id: "hard", label: "Hard" },
];

export function DifficultyTabs({
  value,
  onChange,
}: {
  value: Difficulty | "all";
  onChange: (next: Difficulty | "all") => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Phrase difficulty"
      className="inline-flex items-center gap-0.5 rounded-full border border-line bg-surface/60 p-0.5 backdrop-blur"
    >
      {TABS.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={[
              "press cursor-pointer rounded-full px-3 py-1.5 text-[12px] font-medium tracking-tight",
              active
                ? "bg-ink text-bg"
                : "text-ink-3 hover:text-ink",
            ].join(" ")}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
