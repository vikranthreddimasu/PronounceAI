"use client";

import { useCallback } from "react";
import { tap } from "@/lib/sounds";

export type TabItem<T extends string> = {
  id: T;
  label: string;
  count?: number;
};

type Props<T extends string> = {
  items: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  ariaLabel?: string;
};

export default function Tabs<T extends string>({ items, active, onChange, ariaLabel }: Props<T>) {
  const click = useCallback(
    (id: T) => {
      if (id === active) return;
      tap();
      onChange(id);
    },
    [active, onChange]
  );
  return (
    <div role="tablist" aria-label={ariaLabel} className="tab-bar no-scrollbar" style={{ overflowX: "auto" }}>
      {items.map((it) => (
        <button
          key={it.id}
          role="tab"
          aria-selected={it.id === active}
          data-active={it.id === active}
          className="tab-btn press"
          onClick={() => click(it.id)}
          style={{ whiteSpace: "nowrap" }}
        >
          {it.label}
          {typeof it.count === "number" && (
            <span style={{ opacity: 0.55, marginLeft: 6, fontVariantNumeric: "tabular-nums" }}>
              {it.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
