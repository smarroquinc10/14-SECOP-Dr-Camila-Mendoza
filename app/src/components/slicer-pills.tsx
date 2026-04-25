"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}

/** Excel-slicer-style pills — click to toggle, all options visible. */
export function SlicerPills({ label, options, selected, onChange }: Props) {
  if (options.length === 0) return null;
  const isAllSelected = selected.length === 0;

  function togglePill(opt: string) {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt));
    } else {
      onChange([...selected, opt]);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        {!isAllSelected && (
          <button
            onClick={() => onChange([])}
            className="text-[10px] uppercase tracking-wider text-ink-soft hover:text-burgundy"
          >
            Limpiar
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((opt) => {
          const active = selected.includes(opt);
          return (
            <button
              key={opt}
              onClick={() => togglePill(opt)}
              className={cn(
                "px-3 py-1 text-xs rounded-full border transition-colors",
                active
                  ? "bg-burgundy text-white border-burgundy"
                  : "bg-background border-border text-ink-soft hover:border-burgundy hover:text-ink"
              )}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}
